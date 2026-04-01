FROM python:3.9-slim

WORKDIR /app

# 에뮬레이터에 필요한 paho-mqtt 등 설치용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# 에뮬레이터는 보통 외부 접속을 받기보다 밖으로 쏘는 역할이므로 EXPOSE 생략 가능
# 실행할 스크립트 명시
CMD ["uvicorn", "main:app"]