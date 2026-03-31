# 📡 Sensor Emulator
> 진동 센서 데이터를 시계열로 시뮬레이션하고 MQTT 브로커로 전송하는 데이터 생성기

이 모듈은 실제 하드웨어 센서가 없는 환경에서 개발 및 테스트를 진행하기 위해 제작되었습니다. 
사인파(Sine wave) 기반의 정상 패턴과 사용자 정의 이상 패턴을 생성하여 가상 시리얼 통신(Hex 가공) 방식으로 데이터를 송출합니다.

## 🛠 Tech Stack
- **Language:** Python 3.9+
- **Protocol:** MQTT (Mosquitto)
- **Libraries:** `paho-mqtt`, `numpy`

## 🚀 Getting Started

### 1. Infrastructure (MQTT Broker)
본 에뮬레이터는 MQTT 통신을 위해 `Mosquitto` 브로커를 사용합니다. Docker를 이용해 설정 파일을 마운트하여 실행합니다.

**Mosquitto 설정 (`mosquitto.conf`):**
```conf
listener 1883
allow_anonymous true
```

브로커 실행 (Windows CMD 기준):
docker run -d --name mosquitto -p 1883:1883 -p 9001:9001 -v "%cd%\mosquitto.conf:/mosquitto/config/mosquitto.conf" eclipse-mosquitto

### 2. Environment Setup (Python)
의존성 충돌을 방지하기 위해 가상환경(venv) 사용을 권장합니다.
# 가상환경 생성 및 활성화
python -m venv venv
.\venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

### 3. Running Emulator
uvicorn main:app --reload

## 📂 Key Features
Data Encapsulation: RAW 데이터를 16진수(Hex) 문자열로 인코딩하여 실제 필드 버스 통신과 유사한 데이터 포맷 제공.

Dynamic Waveform: numpy를 활용하여 샘플링 레이트 기반의 정교한 사인파 생성.

Labeling Support: 데이터 패킷 내에 label 필드를 포함하여 AI 학습을 위한 정답지(Ground Truth) 동시 전송.

## 📝 Configuration
MQTT_BROKER: 127.0.0.1 (기본값)

MQTT_TOPIC: sensor/data

SAMPLE_RATE: 1000Hz (초당 128개 샘플씩 묶음 전송)
