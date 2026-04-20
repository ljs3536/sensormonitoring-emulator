import asyncio
import json
import random
import time
import math
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
import paho.mqtt.client as mqtt
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database_rdb import get_db
from sensors import Sensor
import asyncio
import os
app = FastAPI()

templates = Jinja2Templates(directory="templates")

# --- 상태 관리 ---
class EmulatorState:
    def __init__(self):
        self.mode = "stopped" 
        self.sensor_type = "piezo"
        self.sensor_id = ""
        self.interval = 1.0
        self.sample_count = 128
        self.seq = 0
        self.custom_data = {"x": [], "y": [], "z": []}
        self.current_label = "normal"

state = EmulatorState()

# --- MQTT 설정 ---
# 환경변수에 MQTT_BROKER가 있으면 그걸 쓰고, 없으면 "127.0.0.1"을 씁니다.
MQTT_BROKER = os.getenv("MQTT_BROKER", "127.0.0.1") 
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = "sensor/data"

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="FastAPI_Emulator")
mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
mqtt_client.loop_start()

# --- 데이터 생성 루프 ---
async def data_generation_loop():
    print("⚙️ 데이터 생성 루프 백그라운드 구동 시작!") # 루프가 켜졌는지 확인
    while True:
        try:
            if state.mode != "stopped":
                hex_samples = []
                
                # --- (1) 기본 모드 데이터 생성 ---
                if state.mode == "basic_auto":
                    for i in range(state.sample_count):
                        t = (i * 0.01)
                        if state.sensor_type == "piezo":
                            val = int(2048 + 800 * math.sin(t * 10))
                            hex_samples.append(f"{val & 0xFFFF:04X}")
                        else:
                            x = int(2048 + 400 * math.sin(t * 5))
                            y = int(2048 + 300 * math.sin(t * 7))
                            z = int(2048 + 500 * math.sin(t * 3))
                            hex_samples.append(f"{x & 0xFFFF:04X}{y & 0xFFFF:04X}{z & 0xFFFF:04X}")
                            
                # --- (2) 커스텀 모드 데이터 생성 ---
                elif state.mode == "custom_auto":
                    for i in range(state.sample_count):
                        idx = i % len(state.custom_data["x"]) if state.custom_data["x"] else 0
                        if state.sensor_type == "piezo":
                            val = int(state.custom_data["x"][idx]) + random.randint(-10, 10)
                            hex_samples.append(f"{val & 0xFFFF:04X}")
                        else:
                            x = int(state.custom_data["x"][idx]) + random.randint(-5, 5)
                            y = int(state.custom_data["y"][idx]) + random.randint(-5, 5)
                            z = int(state.custom_data["z"][idx]) + random.randint(-5, 5)
                            hex_samples.append(f"{x & 0xFFFF:04X}{y & 0xFFFF:04X}{z & 0xFFFF:04X}")
                
                # --- (3) 페이로드 조립 및 전송 ---
                payload = {
                    "seq": state.seq, 
                    "sensor_id": state.sensor_id, # DB에서 연동한 센서 ID
                    "sensor": state.sensor_type, 
                    "label": state.current_label,
                    "timestamp": time.time(), 
                    "sample_count": state.sample_count, 
                    "hex_data": "".join(hex_samples)
                }
                
                # 🌟 [디버깅] 여기서 발송 여부를 터미널에 찍습니다!
                print(f"📤 MQTT 발송! [ID: {state.sensor_id} | Type: {state.sensor_type} | Mode: {state.mode}]")
                
                mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
                state.seq = (state.seq + 1) % 256
                
        except Exception as e:
            # 🌟 [디버깅] 루프 돌다가 에러 나면 조용히 뻗지 말고 빨간 글씨로 뱉어라!
            print(f"🚨 [에뮬레이터 치명적 에러]: {e}")
            
        await asyncio.sleep(state.interval)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(data_generation_loop())

# --- API 엔드포인트 ---
@app.post("/api/start_basic")
async def start_basic(): state.mode = "basic_auto"; return {"status": "basic_started"}
@app.post("/api/stop")
async def stop_emulator(): state.mode = "stopped"; return {"status": "stopped"}
@app.post("/api/set_sensor/{sensor_type}")
async def set_sensor(sensor_type: str): state.sensor_type = sensor_type; return {"status": "updated"}
@app.post("/api/start_custom")
async def start_custom(request: Request):
    data = await request.json()
    state.custom_data = {"x": data.get("custom_x", []), "y": data.get("custom_y", []), "z": data.get("custom_z", [])}
    state.current_label = data.get("label", "normal")
    state.mode = "custom_auto"
    return {"status": "custom_auto_started"}

@app.get("/api/db_sensors/{sensor_type}")
async def get_sensors_from_db(sensor_type: str, db: Session = Depends(get_db)):
    """MariaDB에서 특정 타입의 활성화된 센서 목록을 가져옵니다."""
    sensors = db.query(Sensor).filter(
        Sensor.type == sensor_type, 
        Sensor.is_active == True
    ).all()
    # 에뮬레이터 UI에서 쓰기 좋게 가공해서 리턴
    return [{"id": s.id, "name": s.name} for s in sensors]

@app.post("/api/set_sensor/{sensor_type}/{sensor_id}")
async def set_sensor(sensor_type: str, sensor_id: str):
    """타입과 함께 선택된 센서 ID를 상태에 업데이트합니다."""
    state.sensor_type = sensor_type
    state.sensor_id = sensor_id
    return {"status": "updated", "type": sensor_type, "id": sensor_id}

# --- 제어 화면 ---
@app.get("/", response_class=HTMLResponse)
async def get_control_panel(request: Request):
    """
    templates/index.html 파일을 읽어서 화면에 뿌려줍니다.
    """
    return templates.TemplateResponse(request=request, name="index.html")