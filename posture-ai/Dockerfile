# syntax=docker/dockerfile:1
# 팀 ai/Dockerfile과 같은 패턴 — 포트만 다르다(8000 vs 8001).
# mediapipe/torch가 없어 ai/ 서버와 비슷한 크기로 유지된다.
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
