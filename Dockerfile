FROM python:3.11-slim

WORKDIR /app

# 에뮬레이터에 필요한 paho-mqtt 등 설치용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# 실행할 스크립트 명시
CMD ["python", "-m","uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]