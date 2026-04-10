import asyncio
import json
import random
import time
import math
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import paho.mqtt.client as mqtt

app = FastAPI()

# --- 상태 관리 (기존과 동일) ---
class EmulatorState:
    def __init__(self):
        self.mode = "stopped" 
        self.sensor_type = "piezo"
        self.interval = 1.0
        self.sample_count = 128
        self.seq = 0
        self.custom_data = {"x": [], "y": [], "z": []}
        self.current_label = "normal" 

state = EmulatorState()

# --- MQTT 설정 (기존과 동일) ---
MQTT_BROKER = "127.0.0.1" 
MQTT_PORT = 1883
MQTT_TOPIC = "sensor/data"
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="FastAPI_Emulator")
mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
mqtt_client.loop_start()

# --- 데이터 생성 루프 (기존과 동일) ---
async def data_generation_loop():
    while True:
        if state.mode != "stopped":
            hex_samples = []
            if state.mode == "basic_auto":
                for i in range(state.sample_count):
                    t = time.time() + (i * 0.01)
                    if state.sensor_type == "piezo":
                        val = int(2048 + 800 * math.sin(t * 10))
                        hex_samples.append(f"{val & 0xFFFF:04X}")
                    else:
                        x = int(2048 + 400 * math.sin(t * 5))
                        y = int(2048 + 300 * math.sin(t * 7))
                        z = int(2048 + 500 * math.sin(t * 3))
                        hex_samples.append(f"{x & 0xFFFF:04X}{y & 0xFFFF:04X}{z & 0xFFFF:04X}")
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
            payload = {"seq": state.seq, "sensor": state.sensor_type, "label": state.current_label, "timestamp": time.time(), "sample_count": state.sample_count, "hex_data": "".join(hex_samples)}
            mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
            state.seq = (state.seq + 1) % 256
        await asyncio.sleep(state.interval)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(data_generation_loop())

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

# --- 제어 화면 (핵심 수정) ---
@app.get("/", response_class=HTMLResponse)
async def get_control_panel():
    html_content = f"""
    <html>
        <head>
            <title>Sensor Emulator Control</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-dragdata@2.2.3/dist/chartjs-plugin-dragdata.min.js"></script>
        </head>
        <body style="font-family: sans-serif; padding: 20px; background-color:#f1f5f9;">
            <div style="max-width: 900px; margin: auto; background: white; padding: 25px; border-radius: 20px; box-shadow: 0 10px 20px rgba(0,0,0,0.1);">
                <h2 style="text-align:center;">🛠️ Sensor Pattern Editor (30-Point Control)</h2>
                
                <div style="display: flex; gap: 20px;">
                    <div style="flex: 1; background: #f8fafc; padding: 15px; border-radius: 12px; border: 1px solid #e2e8f0;">
                        <h4>Control</h4>
                        <button onclick="changeSensor('piezo')" id="btn-piezo" style="width:100%; padding:10px; margin-bottom:5px; background:#3b82f6; color:white; border:none; border-radius:8px; cursor:pointer;">Piezo</button>
                        <button onclick="changeSensor('adxl')" id="btn-adxl" style="width:100%; padding:10px; background:#94a3b8; color:white; border:none; border-radius:8px; cursor:pointer;">ADXL</button>
                        <hr>
                        <button onclick="fetch('/api/start_basic', {{method:'POST'}})" style="width:100%; padding:10px; background:#10b981; color:white; border:none; border-radius:8px; cursor:pointer; margin-bottom:5px;">Auto Generate</button>
                        <button onclick="startCustomLoop()" style="width:100%; padding:10px; background:#6366f1; color:white; border:none; border-radius:8px; cursor:pointer; margin-bottom:5px;">Send Custom Pattern</button>
                        <button onclick="fetch('/api/stop', {{method:'POST'}})" style="width:100%; padding:10px; background:#ef4444; color:white; border:none; border-radius:8px; cursor:pointer;">Stop</button>
                    </div>

                    <div style="flex: 3;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <h4 id="chart-title">Piezo 편집 (30개 점)</h4>
                            <select id="custom_label" style="padding:5px;">
                                <option value="normal">Normal</option>
                                <option value="anomaly">Anomaly</option>
                            </select>
                        </div>
                        <canvas id="dragChart" height="150"></canvas>
                    </div>
                </div>
            </div>

            <script>
                const ctx = document.getElementById('dragChart').getContext('2d');
                let currentType = 'piezo';
                const CONTROL_COUNT = 30; // 제어점 개수
                const TARGET_COUNT = 128; // 실제 전송할 샘플 수

                // 선형 보간 함수: 30개의 점을 128개로 확장
                function interpolate(points, targetLength) {{
                    const result = [];
                    const factor = (points.length - 1) / (targetLength - 1);
                    for (let i = 0; i < targetLength; i++) {{
                        const p = i * factor;
                        const left = Math.floor(p);
                        const right = Math.ceil(p);
                        const weight = p - left;
                        if (left === right) {{
                            result.push(points[left]);
                        }} else {{
                            const val = points[left] * (1 - weight) + points[right] * weight;
                            result.push(Math.round(val));
                        }}
                    }}
                    return result;
                }}

                const datasetPiezo = [
                    {{ label: 'Control Signal', data: Array.from({{length: CONTROL_COUNT}}, () => 2048), borderColor: '#3b82f6', fill: false, tension: 0 }}
                ];
                
                const datasetADXL = [
                    {{ label: 'X', data: Array.from({{length: CONTROL_COUNT}}, () => 2048), borderColor: '#ef4444', tension: 0 }},
                    {{ label: 'Y', data: Array.from({{length: CONTROL_COUNT}}, () => 1800), borderColor: '#22c55e', tension: 0 }},
                    {{ label: 'Z', data: Array.from({{length: CONTROL_COUNT}}, () => 1500), borderColor: '#3b82f6', tension: 0 }}
                ];

                const myChart = new Chart(ctx, {{
                    type: 'line',
                    data: {{ labels: Array.from({{length: CONTROL_COUNT}}, (_, i) => i), datasets: datasetPiezo }},
                    options: {{
                        scales: {{ y: {{ min: 0, max: 4095 }} }},
                        plugins: {{ dragData: {{ round: 0 }} }}
                    }}
                }});

                function changeSensor(type) {{
                    currentType = type;
                    fetch(`/api/set_sensor/${{type}}`, {{method:'POST'}});
                    myChart.data.datasets = (type === 'piezo') ? datasetPiezo : datasetADXL;
                    document.getElementById('chart-title').innerText = type.toUpperCase() + " 편집 (30개 제어점)";
                    myChart.update();
                }}

                async function startCustomLoop() {{
                    // 전송 전 보간 실행
                    const x_full = interpolate(myChart.data.datasets[0].data, TARGET_COUNT);
                    const y_full = (currentType === 'adxl') ? interpolate(myChart.data.datasets[1].data, TARGET_COUNT) : [];
                    const z_full = (currentType === 'adxl') ? interpolate(myChart.data.datasets[2].data, TARGET_COUNT) : [];
                    
                    await fetch('/api/start_custom', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{
                            label: document.getElementById('custom_label').value,
                            custom_x: x_full, custom_y: y_full, custom_z: z_full
                        }})
                    }});
                    alert("30개 점을 128개로 확장하여 전송을 시작합니다! 🚀");
                }}
            </script>
        </body>
    </html>
    """
    return html_content