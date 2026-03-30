import asyncio
import json
import random
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import paho.mqtt.client as mqtt

app = FastAPI()

# --- 상태 관리 ---
class EmulatorState:
    def __init__(self):
        self.is_running = False
        self.sensor_type = "piezo" # 기본값: piezo (또는 adxl)
        self.interval = 1.0        # 1초 주기
        self.min_val = -2000       # 최소 진폭
        self.max_val = 2000        # 최대 진폭
        self.sample_count = 10     # 한 번에 보낼 데이터 개수
        self.seq = 0               # 패킷 순서 확인용
        
state = EmulatorState()

# --- MQTT 클라이언트 설정 ---
MQTT_BROKER = "127.0.0.1" 
MQTT_PORT = 1883
MQTT_TOPIC = "sensor/data"

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="FastAPI_Emulator")

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("✅ MQTT Broker 연결 성공!")
    else:
        print(f"❌ 연결 실패: {reason_code}")

mqtt_client.on_connect = on_connect
mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
mqtt_client.loop_start()

# --- 데이터 생성 및 발행 (Background Task) ---
async def data_generation_loop():
    while True:
        if state.is_running:
            hex_samples = []
            
            # 지정된 개수(sample_count)만큼 데이터를 뽑아서 이어 붙임
            for _ in range(state.sample_count):
                if state.sensor_type == "piezo":
                    raw_val = random.randint(state.min_val, state.max_val)
                    hex_samples.append(f"{raw_val & 0xFFFF:04X}")
                else: # adxl
                    x_val = random.randint(state.min_val, state.max_val)
                    y_val = random.randint(state.min_val, state.max_val)
                    z_val = random.randint(state.min_val, state.max_val)
                    hex_samples.append(f"{x_val & 0xFFFF:04X}{y_val & 0xFFFF:04X}{z_val & 0xFFFF:04X}")

            hex_payload = "".join(hex_samples)

            payload = {
                "seq": state.seq,
                "sensor": state.sensor_type,
                "timestamp": time.time(),
                "sample_count": state.sample_count,
                "hex_data": hex_payload
            }
            
            mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
            print(f"📤 Published [Seq:{state.seq}] {state.sensor_type} ({state.sample_count} samples)")
            
            state.seq = (state.seq + 1) % 256 # 0~255 반복
            
        await asyncio.sleep(state.interval)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(data_generation_loop())

# --- API 엔드포인트 ---
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

# 파라미터 업데이트 API 추가
@app.post("/api/update_params")
async def update_params(request: Request):
    data = await request.json()
    state.min_val = int(data.get("min_val", state.min_val))
    state.max_val = int(data.get("max_val", state.max_val))
    state.sample_count = int(data.get("sample_count", state.sample_count))
    state.interval = float(data.get("interval", state.interval))
    print(f"⚙️ Params Updated: {data}")
    return {"status": "params_updated"}

# --- 제어 화면 (업데이트) ---
@app.get("/", response_class=HTMLResponse)
async def get_control_panel():
    html_content = f"""
    <html>
        <head><title>Sensor Emulator Control</title></head>
        <body style="font-family: Arial; padding: 20px;">
            <h2>MQTT Sensor Emulator</h2>
            
            <div style="margin-bottom: 20px; padding: 10px; border: 1px solid #ccc;">
                <strong>1. 기본 제어</strong><br><br>
                <button onclick="fetch('/api/start', {{method:'POST'}})">Start Sending</button>
                <button onclick="fetch('/api/stop', {{method:'POST'}})">Stop Sending</button>
                <button onclick="fetch('/api/set_sensor/piezo', {{method:'POST'}})">Set Piezo</button>
                <button onclick="fetch('/api/set_sensor/adxl', {{method:'POST'}})">Set ADXL</button>
            </div>

            <div style="padding: 10px; border: 1px solid #ccc;">
                <strong>2. 상세 파라미터 설정</strong><br><br>
                Min Value: <input type="number" id="min_val" value="{state.min_val}"><br><br>
                Max Value: <input type="number" id="max_val" value="{state.max_val}"><br><br>
                Sample Count (1회 전송 개수): <input type="number" id="sample_count" value="{state.sample_count}"><br><br>
                Interval (초 단위): <input type="number" step="0.1" id="interval" value="{state.interval}"><br><br>
                <button onclick="updateParams()">적용하기 (Apply)</button>
            </div>

            <script>
                async function updateParams() {{
                    const payload = {{
                        min_val: document.getElementById('min_val').value,
                        max_val: document.getElementById('max_val').value,
                        sample_count: document.getElementById('sample_count').value,
                        interval: document.getElementById('interval').value
                    }};
                    
                    await fetch('/api/update_params', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(payload)
                    }});
                    alert("파라미터가 적용되었습니다!");
                }}
            </script>
        </body>
    </html>
    """
    return html_content