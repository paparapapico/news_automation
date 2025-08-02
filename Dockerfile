# Railway 최적화 Dockerfile - ALSA 오류 해결
FROM python:3.11-slim

# 시스템 패키지 최소화 설치 (ALSA 관련 제거)
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# Python 버퍼링 비활성화
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ALSA 오류 방지
ENV ALSA_PCM_CARD=default
ENV ALSA_PCM_DEVICE=0

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 파일 복사
COPY . .

# 필요한 디렉토리 생성
RUN mkdir -p uploads generated_videos generated_audio temp logs

# Railway 환경 설정
ENV RAILWAY=true
ENV ENVIRONMENT=production

# 시작 스크립트 복사 및 실행 권한 부여
COPY start.sh .
RUN chmod +x start.sh

# 포트 노출
EXPOSE 8000

# 시작 스크립트로 애플리케이션 실행
CMD ["./start.sh"]