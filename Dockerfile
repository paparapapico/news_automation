# Railway용 Dockerfile - 포트 문제 해결
FROM python:3.11-slim

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libfontconfig1 \
    libxrender1 \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 파일 복사
COPY . .

# 필요한 디렉토리 생성
RUN mkdir -p uploads generated_videos generated_audio temp

# Railway 환경 설정
ENV RAILWAY=true
ENV ENVIRONMENT=production

# 포트 설정 - Railway가 자동으로 제공
EXPOSE $PORT

# 애플리케이션 실행 - Railway 포트 사용
CMD uvicorn clean_news_automation:app --host 0.0.0.0 --port ${PORT:-8000}