#!/bin/bash

# Railway 시작 스크립트 - 포트 문제 해결

# PORT 환경변수가 설정되어 있는지 확인
if [ -z "$PORT" ]; then
    echo "⚠️ PORT 환경변수가 설정되지 않음. 기본 포트 8000 사용"
    export PORT=8000
else
    echo "✅ PORT 환경변수 설정됨: $PORT"
fi

# Railway 환경 설정
export RAILWAY=true
export ENVIRONMENT=production

echo "🚀 Railway에서 앱 시작 중..."
echo "📍 포트: $PORT"
echo "🌐 호스트: 0.0.0.0"

# uvicorn으로 앱 실행
exec uvicorn clean_news_automation:app --host 0.0.0.0 --port $PORT