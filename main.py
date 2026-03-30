import asyncio
import json
import random
import time
import math
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import paho.mqtt.client as mqtt

app = FastAPI()

# --- 상태 관리 ---
class EmulatorState:
    def __init__(self):
        # 모드: "stopped", "basic_auto" (간편생성), "custom_auto" (그린거 무한전송)
        self.mode = "stopped" 
        self.sensor_type = "piezo"
        self.interval = 1.0
        self.min_val = -2000
        self.max_val = 2000
        self.sample_count = 128
        self.seq = 0
        
        # 커스텀 데이터 전송용
        self.custom_data = []
        self.current_label = "normal" 

state = EmulatorState()

# --- MQTT 설정 ---
MQTT_BROKER = "127.0.0.1" 
MQTT_PORT = 1883
MQTT_TOPIC = "sensor/data"

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="FastAPI_Emulator")
mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
mqtt_client.loop_start()

# --- 자동 데이터 생성 루프 ---
async def data_generation_loop():
    while True:
        if state.mode != "stopped":
            hex_samples = []
            
            # 1. 간편 자동 생성 모드 (기존 Start Auto)
            if state.mode == "basic_auto":
                state.current_label = "normal" # 간편 생성은 무조건 정상 라벨
                amplitude = (state.max_val - state.min_val) / 2
                offset = state.min_val + amplitude

                for i in range(state.sample_count):
                    time_tick = state.seq * state.sample_count + i
                    if state.sensor_type == "piezo":
                        wave = math.sin(time_tick * 0.1) 
                        raw_val = int(offset + (wave * amplitude) + random.randint(-50, 50))
                        hex_samples.append(f"{raw_val & 0xFFFF:04X}")
                    else: # ADXL
                        wave_x = math.sin(time_tick * 0.1)
                        wave_y = math.sin(time_tick * 0.15 + 1.0)
                        wave_z = math.sin(time_tick * 0.05 + 2.0)
                        x_val = int(offset + (wave_x * amplitude) + random.randint(-20, 20))
                        y_val = int(offset + (wave_y * amplitude) + random.randint(-20, 20))
                        z_val = int(offset + (wave_z * amplitude) + random.randint(-20, 20))
                        hex_samples.append(f"{x_val & 0xFFFF:04X}{y_val & 0xFFFF:04X}{z_val & 0xFFFF:04X}")

            # 2. 내가 그린 데이터 무한 전송 모드 (새로운 기능)
            elif state.mode == "custom_auto" and state.custom_data:
                for base_val in state.custom_data:
                    # 그린 데이터에 약간의 노이즈를 섞어 실제 센서처럼 연출
                    raw_val = int(base_val) + random.randint(-30, 30)
                    
                    if state.sensor_type == "piezo":
                        hex_samples.append(f"{raw_val & 0xFFFF:04X}")
                    else:
                        hex_samples.append(f"{raw_val & 0xFFFF:04X}{0 & 0xFFFF:04X}{0 & 0xFFFF:04X}")

            # MQTT 페이로드 전송 (🔥 라벨 정보 추가됨!)
            payload = {
                "seq": state.seq,
                "sensor": state.sensor_type,
                "label": state.current_label, # normal 또는 anomaly 등
                "timestamp": time.time(),
                "sample_count": state.sample_count,
                "hex_data": "".join(hex_samples)
            }
            mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
            print(f"📤 [{state.mode.upper()}] {state.sensor_type} | Label: {state.current_label} | Seq: {state.seq}")
            state.seq = (state.seq + 1) % 256
            
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

# 🌟 [NEW] 마우스로 그린 데이터를 무한 반복 전송하는 API
@app.post("/api/start_custom")
async def start_custom(request: Request):
    data = await request.json()
    state.custom_data = data.get("custom_data", [])
    state.current_label = data.get("label", "normal") # 프론트에서 넘어온 라벨 저장
    state.mode = "custom_auto"
    return {"status": "custom_auto_started", "label": state.current_label}

# --- 제어 화면 ---
@app.get("/", response_class=HTMLResponse)
async def get_control_panel():
    html_content = f"""
    <html>
        <head>
            <title>Sensor Emulator Control</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-dragdata@2.2.3/dist/chartjs-plugin-dragdata.min.js"></script>
        </head>
        <body style="font-family: Arial; padding: 20px; background-color:#f9fafb;">
            <h2>🚀 Ultimate MQTT Sensor Emulator</h2>
            
            <div style="display: flex; gap: 20px;">
                <div style="flex: 1; padding: 20px; background: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <h3>1. 간편 자동 생성 (Basic Auto)</h3>
                    <p style="font-size:12px; color:gray;">수학 공식(Sin) 기반의 정상 데이터를 계속 보냅니다.</p>
                    <button onclick="fetch('/api/start_basic', {{method:'POST'}})">Start Auto</button>
                    <button onclick="fetch('/api/stop', {{method:'POST'}})" style="background:#ef4444; color:white;">Stop All</button>
                    <hr style="margin: 15px 0;">
                    Sensor: 
                    <button onclick="fetch('/api/set_sensor/piezo', {{method:'POST'}})">Piezo</button>
                    <button onclick="fetch('/api/set_sensor/adxl', {{method:'POST'}})">ADXL</button>
                </div>

                <div style="flex: 2; padding: 20px; background: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                    <h3>🎨 2. 그래프 그려서 반복 전송하기</h3>
                    <div style="margin-bottom: 15px; background: #f3f4f6; padding: 10px; border-radius: 8px;">
                        <label style="font-weight:bold; margin-right:10px;">데이터 라벨(Label) 선택:</label>
                        <select id="custom_label" style="padding: 5px;">
                            <option value="normal">✅ 정상 (Normal)</option>
                            <option value="anomaly">⚠️ 비정상 (Anomaly)</option>
                            <option value="error_type_a">❌ 고장 A유형</option>
                        </select>
                        <button onclick="startCustomLoop()" style="margin-left:15px; background: #4f46e5; color: white; padding: 8px 15px; border: none; border-radius: 5px; cursor: pointer;">
                            이 그래프로 반복 전송 시작
                        </button>
                    </div>
                    <canvas id="dragChart" height="80"></canvas>
                </div>
            </div>

            <script>
                let initialData = [];
                for(let i=0; i<128; i++) {{ initialData.push(Math.sin(i * 0.1) * 1000); }}

                const ctx = document.getElementById('dragChart').getContext('2d');
                const myChart = new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: Array.from({{length: 128}}, (_, i) => i),
                        datasets: [{{
                            label: 'Drag Points to Create Pattern',
                            data: initialData,
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59, 130, 246, 0.2)',
                            pointBackgroundColor: '#ef4444',
                            pointRadius: 4, pointHoverRadius: 8, fill: true, tension: 0.4
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        scales: {{ y: {{ min: -4000, max: 4000 }} }},
                        plugins: {{
                            dragData: {{ round: 1, showTooltip: true }}
                        }}
                    }}
                }});

                // 그린 데이터를 라벨과 함께 백엔드로 반복 전송 요청
                async function startCustomLoop() {{
                    const currentData = myChart.data.datasets[0].data;
                    const selectedLabel = document.getElementById('custom_label').value;
                    
                    await fetch('/api/start_custom', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ 
                            custom_data: currentData,
                            label: selectedLabel 
                        }})
                    }});
                    
                    alert(`[${{selectedLabel.toUpperCase()}}] 라벨로\\n그래프 데이터 무한 반복 전송을 시작합니다! 🚀`);
                }}
            </script>
        </body>
    </html>
    """
    return html_content