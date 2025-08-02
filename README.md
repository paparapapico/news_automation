# 🚀 AI News Automation & Reels Platform

AI 기반 뉴스 자동화 및 Instagram 릴스 제작 플랫폼

## ✨ 주요 기능

- 🔍 **다중 소스 뉴스 크롤링** (Google News)
- 🤖 **AI 바이럴 캡션 생성**
- 🎬 **자동 릴스 제작** (TTS + 비주얼)
- 📱 **Instagram 릴스 자동 업로드**
- 📊 **바이럴 점수 기반 우선순위**
- 📈 **성과 분석 및 모니터링**

## 🛠️ 기술 스택

- **Backend**: FastAPI, Python 3.11+
- **AI**: OpenAI GPT, TTS
- **Video Processing**: MoviePy, OpenCV
- **Database**: SQLite/PostgreSQL
- **Deployment**: Railway, Docker

## 📋 설치 및 실행

### 1. 저장소 클론
```bash
git clone https://github.com/your-username/news-automation.git
cd news-automation
```

### 2. 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate  # Windows
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. 환경변수 설정
`.env` 파일을 생성하고 다음 내용을 추가:
```env
OPENAI_API_KEY=your_openai_api_key
INSTAGRAM_ACCESS_TOKEN=your_instagram_access_token
DATABASE_URL=sqlite:///./news_automation.db
```

### 5. 애플리케이션 실행
```bash
# 개발 서버 실행
uvicorn clean_news_automation:app --reload

# 또는
python clean_news_automation.py
```

## 🌐 접속 URL

- **API 서버**: http://127.0.0.1:8000
- **대시보드**: http://127.0.0.1:8000/dashboard
- **API 문서**: http://127.0.0.1:8000/docs

## 📱 API 엔드포인트

### 뉴스 관련
- `GET /api/news/trending` - 트렌딩 뉴스 조회
- `POST /api/news/crawl` - 뉴스 크롤링 실행

### 릴스 관련
- `GET /api/reels/recent` - 최근 릴스 조회
- `POST /api/reels/generate/{news_id}` - 릴스 생성
- `POST /api/reels/upload/{reel_id}` - 릴스 업로드

### 분석
- `GET /api/analytics/performance` - 성과 분석

## 🚀 배포

### Railway 배포
1. GitHub에 코드 푸시
2. Railway 계정 생성
3. GitHub 저장소 연결
4. 환경변수 설정
5. 자동 배포

### Docker 배포
```bash
docker build -t news-automation .
docker run -p 8000:8000 news-automation
```

## 📁 프로젝트 구조

```
news-automation/
├── clean_news_automation.py    # 메인 애플리케이션
├── requirements.txt           # Python 의존성
├── .env.example              # 환경변수 예시
├── .gitignore               # Git 제외 파일
├── README.md               # 프로젝트 문서
├── generated_videos/       # 생성된 비디오 파일
├── generated_images/       # 생성된 이미지 파일
└── logs/                  # 로그 파일
```

## 🔧 환경변수

| 변수명 | 설명 | 필수 |
|--------|------|------|
| `OPENAI_API_KEY` | OpenAI API 키 | ✅ |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram API 토큰 | ✅ |
| `DATABASE_URL` | 데이터베이스 URL | ✅ |

## 🤝 기여하기

1. Fork 프로젝트
2. Feature 브랜치 생성 (`git checkout -b feature/amazing-feature`)
3. 변경사항 커밋 (`git commit -m 'Add amazing feature'`)
4. 브랜치에 Push (`git push origin feature/amazing-feature`)
5. Pull Request 생성

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 🐛 버그 리포트

버그를 발견하시면 [Issues](https://github.com/your-username/news-automation/issues)에 리포트해주세요.

## 📞 문의

프로젝트 관련 문의사항이 있으시면 이슈를 생성해주세요.
# news_automation
good
