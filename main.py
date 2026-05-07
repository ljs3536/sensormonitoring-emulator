import json
import time
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
import paho.mqtt.client as mqtt
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database_rdb import get_db
from sensors import Sensor
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- 상태 관리 (루프 상태 제거, 시퀀스와 센서 정보만 유지) ---
class EmulatorState:
    def __init__(self):
        self.sensor_type = "piezo"
        self.sensor_id = ""
        self.seq = 0

state = EmulatorState()

# --- MQTT 설정 ---
MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1") 
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = "sensor/data"

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="FastAPI_Emulator")
mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
mqtt_client.loop_start()

# --- API 엔드포인트 ---

@app.get("/api/db_sensors/{sensor_type}")
async def get_sensors_from_db(sensor_type: str, db: Session = Depends(get_db)):
    """MariaDB에서 특정 타입의 활성화된 센서 목록과 물리 파라미터를 가져옵니다."""
    sensors = db.query(Sensor).filter(
        Sensor.type == sensor_type, 
        Sensor.is_active == True
    ).all()
    
    # 🌟 프론트엔드(index.html)에서 물리 공식을 계산할 수 있도록 k, c, temp를 함께 리턴합니다!
    return [{
        "id": s.id, 
        "name": s.name,
        "physics_k": s.physics_k,
        "physics_c": s.physics_c,
        "ambient_temp": s.ambient_temp
    } for s in sensors]

@app.post("/api/set_sensor/{sensor_type}/{sensor_id}")
async def set_sensor(sensor_type: str, sensor_id: str):
    """타입과 함께 선택된 센서 ID를 상태에 업데이트합니다."""
    state.sensor_type = sensor_type
    state.sensor_id = sensor_id
    return {"status": "updated", "type": sensor_type, "id": sensor_id}

@app.post("/api/start_custom")
async def start_custom(request: Request):
    """프론트엔드 화면에서 계산되어 넘어온 데이터를 즉시 Hex로 변환하여 MQTT로 릴레이합니다."""
    data = await request.json()
    
    custom_x = data.get("custom_x", [])
    custom_y = data.get("custom_y", [])
    custom_z = data.get("custom_z", [])
    label = data.get("label", "normal")
    
    sample_count = len(custom_x)
    hex_samples = []

    # 1. 화면에서 넘어온 정수 배열을 16진수(Hex) 포맷으로 변환
    if state.sensor_type == "piezo":
        for val in custom_x:
            v = int(val)
            hex_samples.append(f"{v & 0xFFFF:04X}")
    else:
        for x, y, z in zip(custom_x, custom_y, custom_z):
            xi, yi, zi = int(x), int(y), int(z)
            hex_samples.append(f"{xi & 0xFFFF:04X}{yi & 0xFFFF:04X}{zi & 0xFFFF:04X}")

    hex_data_str = "".join(hex_samples)

    # 2. 콜렉터가 수신할 MQTT 페이로드 조립
    payload = {
        "seq": state.seq, 
        "sensor_id": state.sensor_id,
        "sensor": state.sensor_type, 
        "label": label,
        "timestamp": time.time(), 
        "sample_count": sample_count, 
        "hex_data": hex_data_str
    }
    
    # 3. MQTT 발송
    print(f"📤 [Relay] MQTT 발송! [ID: {state.sensor_id} | Type: {state.sensor_type} | Label: {label} | Data Length: {sample_count}]")
    mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
    
    state.seq = (state.seq + 1) % 256
    return {"status": "sent_to_mqtt"}

# --- 화면 렌더링 ---
@app.get("/", response_class=HTMLResponse)
async def get_control_panel(request: Request):
    """templates/index.html 파일을 읽어서 화면에 뿌려줍니다."""
    return templates.TemplateResponse(request=request, name="index.html")


# 🌟 1. 새로운 FFT 전용 컨트롤 패널 화면 서빙
@app.get("/fft", response_class=HTMLResponse)
async def get_fft_control_panel(request: Request):
    """templates/fft_index.html 파일을 읽어서 화면에 뿌려줍니다."""
    return templates.TemplateResponse(request=request, name="fft_index.html")

# 🌟 2. 화면에서 만든 FFT 데이터를 받아 MQTT로 직행하는 API
@app.post("/api/start_fft_custom")
async def start_fft_custom(request: Request):
    """프론트엔드에서 파이프(|)로 조인되어 넘어온 데이터를 그대로 MQTT로 릴레이합니다."""
    data = await request.json()
    
    fft_data_str = data.get("fft_data", "")
    label = data.get("label", "normal")
    
    # 앞서 수정한 Collector가 받을 수 있는 포맷으로 조립
    payload = {
        "seq": state.seq, 
        "sensor_id": "piezo_01",
        "sensor": "normal", 
        "label": label,
        "timestamp": time.time(), 
        "hex_data": fft_data_str, # Hex 데이터 대신 FFT 문자열 삽입!
        "battery": 100
    }
    
    # 3. MQTT 발송
    print(f"📤 [FFT Direct] MQTT 발송! [ID: {state.sensor_id} | Label: {label}]")
    mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
    
    state.seq = (state.seq + 1) % 256
    return {"status": "sent_fft_to_mqtt"}

