import asyncio
import json
import random
import time
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse
import paho.mqtt.client as mqtt

app = FastAPI()

# --- 상태 관리 ---
class EmulatorState:
    def __init__(self):
        self.is_running = False
        self.sensor_type = "piezo" # 기본값: piezo (또는 adxl)
        self.interval = 1.0        # 1초 주기

state = EmulatorState()

# --- MQTT 클라이언트 설정 ---
MQTT_BROKER = "127.0.0.1" # Docker로 띄운 Mosquitto
MQTT_PORT = 1883
MQTT_TOPIC = "sensor/data"

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="FastAPI_Emulator")

# --- 콜백 함수 추가 ---
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("✅ MQTT Broker 연결 성공!")
    else:
        print(f"❌ 연결 실패: {reason_code}")

mqtt_client.on_connect = on_connect
# --------------------

mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
mqtt_client.loop_start()

# --- 데이터 생성 및 발행 (Background Task) ---
async def data_generation_loop():
    while True:
        if state.is_running:
            if state.sensor_type == "piezo":
                # 예: 0 ~ 5000 사이의 값을 생성하여 16비트 Hex로 변환 (4자리)
                raw_val = random.randint(0, 5000)
                hex_payload = f"{raw_val & 0xFFFF:04X}"
                
            else: # adxl
                # 예: -2000 ~ 2000 사이의 값을 생성하여 각각 16비트 Hex로 변환 (총 12자리)
                x_val = random.randint(-2000, 2000)
                y_val = random.randint(-2000, 2000)
                z_val = random.randint(-2000, 2000)
                hex_payload = f"{x_val & 0xFFFF:04X}{y_val & 0xFFFF:04X}{z_val & 0xFFFF:04X}"

            # JSON에는 센서 타입과 Raw Hex String만 담아서 전송
            payload = {
                "sensor": state.sensor_type,
                "timestamp": time.time(),
                "hex_data": hex_payload
            }
            
            mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
            print(f"📤 Published Raw: {payload}")
            
        await asyncio.sleep(state.interval)

# FastAPI 시작 시 백그라운드 루프 실행
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(data_generation_loop())

# --- API 엔드포인트 (컨트롤 용도) ---
@app.post("/api/start")
async def start_emulator():
    state.is_running = True
    return {"status": "started", "sensor": state.sensor_type}

@app.post("/api/stop")
async def stop_emulator():
    state.is_running = False
    return {"status": "stopped"}

@app.post("/api/set_sensor/{sensor_type}")
async def set_sensor(sensor_type: str):
    if sensor_type in ["piezo", "adxl"]:
        state.sensor_type = sensor_type
        return {"status": "updated", "sensor": state.sensor_type}
    return {"error": "Invalid sensor type"}

# --- 간단한 제어 화면 (프론트엔드 통합 전 임시 테스트용) ---
@app.get("/", response_class=HTMLResponse)
async def get_control_panel():
    html_content = """
    <html>
        <head><title>Sensor Emulator Control</title></head>
        <body>
            <h1>MQTT Sensor Emulator</h1>
            <button onclick="fetch('/api/start', {method:'POST'})">Start Sending</button>
            <button onclick="fetch('/api/stop', {method:'POST'})">Stop Sending</button>
            <br><br>
            <button onclick="fetch('/api/set_sensor/piezo', {method:'POST'})">Set Piezo</button>
            <button onclick="fetch('/api/set_sensor/adxl', {method:'POST'})">Set ADXL</button>
        </body>
    </html>
    """
    return html_content