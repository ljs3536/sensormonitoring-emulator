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
        self.mode = "stopped"  # "stopped", "basic_auto", "custom_auto"
        self.sensor_type = "piezo"
        self.interval = 1.0
        self.sample_count = 128
        self.seq = 0
        
        # 커스텀 데이터 저장소
        self.custom_data = {"x": [], "y": [], "z": []}
        self.current_label = "normal" 

state = EmulatorState()

# --- MQTT 설정 ---
MQTT_BROKER = "127.0.0.1" 
MQTT_PORT = 1883
MQTT_TOPIC = "sensor/data"

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="FastAPI_Emulator")
mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
mqtt_client.loop_start()

# --- 데이터 생성 및 전송 루프 ---
async def data_generation_loop():
    while True:
        if state.mode != "stopped":
            hex_samples = []
            t_base = time.time()
            
            # 1. [RESTORED] 간편 자동 생성 모드 (수학 공식 기반)
            if state.mode == "basic_auto":
                state.current_label = "normal"
                for i in range(state.sample_count):
                    t = t_base + (i * 0.01)
                    if state.sensor_type == "piezo":
                        val = int(2048 + 800 * math.sin(t * 10) + random.randint(-50, 50))
                        hex_samples.append(f"{val & 0xFFFF:04X}")
                    else:
                        # ADXL 3축 자동 생성 (각기 다른 파형 부여)
                        x = int(2048 + 400 * math.sin(t * 5))
                        y = int(2048 + 300 * math.sin(t * 7 + 1.5))
                        z = int(2048 + 500 * math.sin(t * 3 + 0.5))
                        hex_samples.append(f"{x & 0xFFFF:04X}{y & 0xFFFF:04X}{z & 0xFFFF:04X}")

            # 2. 커스텀 데이터 전송 모드 (UI에서 그린 데이터 사용)
            elif state.mode == "custom_auto":
                for i in range(state.sample_count):
                    idx = i % len(state.custom_data["x"]) if state.custom_data["x"] else 0
                    if state.sensor_type == "piezo":
                        val = int(state.custom_data["x"][idx]) + random.randint(-15, 15)
                        hex_samples.append(f"{val & 0xFFFF:04X}")
                    else:
                        x = int(state.custom_data["x"][idx]) + random.randint(-5, 5)
                        y = int(state.custom_data["y"][idx]) + random.randint(-5, 5)
                        z = int(state.custom_data["z"][idx]) + random.randint(-5, 5)
                        hex_samples.append(f"{x & 0xFFFF:04X}{y & 0xFFFF:04X}{z & 0xFFFF:04X}")

            # MQTT 전송
            payload = {
                "seq": state.seq,
                "sensor": state.sensor_type,
                "label": state.current_label,
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

@app.post("/api/start_custom")
async def start_custom(request: Request):
    data = await request.json()
    state.custom_data = {
        "x": data.get("custom_x", []),
        "y": data.get("custom_y", []),
        "z": data.get("custom_z", [])
    }
    state.current_label = data.get("label", "normal")
    state.mode = "custom_auto"
    return {"status": "custom_auto_started"}

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
        <body style="font-family: Arial; padding: 20px; background-color:#f1f5f9;">
            <div style="max-width: 1000px; margin: auto; background: white; padding: 30px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.1);">
                <h2 style="text-align:center; color:#0f172a;">🛰️ Multi-Sensor Emulator Dashboard</h2>
                
                <div style="display: flex; gap: 20px; margin-top: 30px;">
                    <div style="flex: 1; display: flex; flex-direction: column; gap: 15px;">
                        <div style="background: #e2e8f0; padding: 15px; border-radius: 12px;">
                            <h4 style="margin-top:0;">1단계: 센서 선택</h4>
                            <button onclick="changeSensor('piezo')" id="btn-piezo" style="width:100%; padding:10px; margin-bottom:5px; border-radius:8px; cursor:pointer; background:#3b82f6; color:white; border:none;">Piezo (1축)</button>
                            <button onclick="changeSensor('adxl')" id="btn-adxl" style="width:100%; padding:10px; border-radius:8px; cursor:pointer; background:#94a3b8; color:white; border:none;">ADXL (3축)</button>
                        </div>
                        
                        <div style="background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #cbd5e1;">
                            <h4 style="margin-top:0;">2단계: 동작 제어</h4>
                            <button onclick="fetch('/api/start_basic', {{method:'POST'}})" style="width:100%; padding:12px; background:#10b981; color:white; border:none; border-radius:8px; cursor:pointer; margin-bottom:10px;">✨ 자동 생성 시작 (Auto)</button>
                            <button onclick="startCustomLoop()" style="width:100%; padding:12px; background:#6366f1; color:white; border:none; border-radius:8px; cursor:pointer; margin-bottom:10px;">🎨 그린 패턴 전송 (Custom)</button>
                            <button onclick="fetch('/api/stop', {{method:'POST'}})" style="width:100%; padding:12px; background:#ef4444; color:white; border:none; border-radius:8px; cursor:pointer;">🛑 전송 중단</button>
                        </div>
                    </div>

                    <div style="flex: 2; background: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e2e8f0;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <h4 id="chart-title" style="margin:0;">Piezo 패턴 편집</h4>
                            <select id="custom_label" style="padding: 5px; border-radius: 5px;">
                                <option value="normal">✅ 정상(Normal)</option>
                                <option value="anomaly">⚠️ 비정상(Anomaly)</option>
                                <option value="error">❌ 고장(Error)</option>
                            </select>
                        </div>
                        <canvas id="dragChart" height="150"></canvas>
                    </div>
                </div>
            </div>

            <script>
                const ctx = document.getElementById('dragChart').getContext('2d');
                let currentType = 'piezo';

                const datasetPiezo = [
                    {{ label: 'Piezo', data: Array.from({{length: 128}}, (_, i) => Math.sin(i * 0.1) * 1000), borderColor: '#3b82f6', fill: true, backgroundColor: 'rgba(59, 130, 246, 0.1)', tension: 0.4 }}
                ];
                
                const datasetADXL = [
                    {{ label: 'X-Axis', data: Array.from({{length: 128}}, (_, i) => Math.sin(i * 0.1) * 1000), borderColor: '#ef4444', tension: 0.4 }},
                    {{ label: 'Y-Axis', data: Array.from({{length: 128}}, (_, i) => Math.cos(i * 0.1) * 800), borderColor: '#22c55e', tension: 0.4 }},
                    {{ label: 'Z-Axis', data: Array.from({{length: 128}}, (_, i) => Math.sin(i * 0.05) * 500), borderColor: '#3b82f6', tension: 0.4 }}
                ];

                const myChart = new Chart(ctx, {{
                    type: 'line',
                    data: {{ labels: Array.from({{length: 128}}, (_, i) => i), datasets: datasetPiezo }},
                    options: {{
                        responsive: true,
                        scales: {{ y: {{ min: -4000, max: 4000 }} }},
                        plugins: {{ dragData: {{ round: 1 }} }}
                    }}
                }});

                async function changeSensor(type) {{
                    currentType = type;
                    await fetch(`/api/set_sensor/${{type}}`, {{method:'POST'}});
                    
                    if(type === 'piezo') {{
                        myChart.data.datasets = datasetPiezo;
                        document.getElementById('chart-title').innerText = "Piezo 패턴 편집";
                        document.getElementById('btn-piezo').style.background = '#3b82f6';
                        document.getElementById('btn-adxl').style.background = '#94a3b8';
                    }} else {{
                        myChart.data.datasets = datasetADXL;
                        document.getElementById('chart-title').innerText = "ADXL 패턴 편집 (X,Y,Z)";
                        document.getElementById('btn-adxl').style.background = '#3b82f6';
                        document.getElementById('btn-piezo').style.background = '#94a3b8';
                    }}
                    myChart.update();
                }}

                async function startCustomLoop() {{
                    const label = document.getElementById('custom_label').value;
                    const body = {{
                        label: label,
                        custom_x: myChart.data.datasets[0].data,
                        custom_y: currentType === 'adxl' ? myChart.data.datasets[1].data : [],
                        custom_z: currentType === 'adxl' ? myChart.data.datasets[2].data : []
                    }};
                    await fetch('/api/start_custom', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(body)
                    }});
                }}
            </script>
        </body>
    </html>
    """
    return html_content