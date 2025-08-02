# clean_news_automation.py - 개선된 뉴스 & 릴스 자동화 백엔드
from fastapi import FastAPI, Request, Depends, HTTPException, Response, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import hashlib
import secrets
import os
import sqlite3
from datetime import datetime, timedelta
import uvicorn
import json
from typing import Optional, Dict, Any, List
import requests
import asyncio
import logging
import jwt
import random
from pydantic import BaseModel
import aiohttp
from bs4 import BeautifulSoup
import feedparser
import re
from urllib.parse import urlparse, urljoin
import time
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import tempfile
import urllib.parse
import subprocess
import cv2
import numpy as np
import gtts
from io import BytesIO
import base64
import shutil

# ===== 로깅 설정 (가장 먼저!) =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===== 환경변수 로드 =====
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("✅ 환경변수 로드 완료")
except ImportError:
    logger.warning("⚠️ dotenv 없음 - 환경변수를 직접 설정하세요")
except Exception as e:
    logger.warning(f"⚠️ 환경변수 로드 오류: {e}")

# ===== 환경 감지 =====
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
IS_RENDER = bool(os.getenv('RENDER'))
IS_PRODUCTION = ENVIRONMENT == 'production' or IS_RENDER

if IS_RENDER:
    logger.info("🌐 Render 환경에서 실행 중")
else:
    logger.info("💻 로컬 환경에서 실행 중")

# ===== 기본 설정 =====
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true' and not IS_PRODUCTION
HOST = os.getenv('HOST', '127.0.0.1')
PORT = int(os.getenv('PORT', 8000))

# 파일 경로 설정
UPLOAD_DIR = "uploads"
VIDEO_OUTPUT_DIR = "generated_videos"
AUDIO_OUTPUT_DIR = "generated_audio"
TEMP_DIR = "temp"

# 디렉토리 생성 (안전하게)
for directory in [UPLOAD_DIR, VIDEO_OUTPUT_DIR, AUDIO_OUTPUT_DIR, TEMP_DIR]:
    try:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"✅ 디렉토리 생성/확인: {directory}")
    except Exception as e:
        logger.warning(f"⚠️ 디렉토리 생성 실패: {directory} - {e}")

# JWT 설정
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-this-in-production')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# 보안 설정
security = HTTPBearer(auto_error=False)

# OpenAI 가져오기
try:
    import openai
    openai_version = openai.__version__
    logger.info(f"📦 OpenAI 버전: {openai_version}")
    
    if openai_version.startswith('1.'):
        OPENAI_V1 = True
    else:
        OPENAI_V1 = False
        
except ImportError:
    logger.warning("❌ OpenAI 라이브러리가 설치되지 않았습니다.")
    OPENAI_V1 = False

# MoviePy 체크
try:
    from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
    MOVIEPY_AVAILABLE = True
    logger.info("✅ MoviePy 사용 가능")
except ImportError:
    MOVIEPY_AVAILABLE = False
    logger.warning("⚠️ MoviePy 없음 - 기본 비디오만 생성됩니다")

# 뉴스 카테고리 설정
NEWS_CATEGORIES = {
    "stock": {
        "name": "주식·경제",
        "keywords": ["주식", "증시", "코스피", "나스닥", "삼성전자", "경제", "금리", "환율", "비트코인", "암호화폐"],
        "search_terms": ["stock market", "nasdaq", "kospi", "economy", "finance", "bitcoin", "cryptocurrency"],
        "trending_terms": ["급등", "폭락", "상한가", "하한가", "사상최고가", "급락"]
    },
    "politics": {
        "name": "정치",
        "keywords": ["대통령", "국회", "정치", "선거", "정부", "여야", "정치인", "국정감사"],
        "search_terms": ["politics", "president", "government", "election", "korea politics"],
        "trending_terms": ["긴급", "속보", "논란", "발언", "회견"]
    },
    "international": {
        "name": "해외 이슈",
        "keywords": ["미국", "중국", "일본", "전쟁", "국제", "외교", "트럼프", "바이든"],
        "search_terms": ["international", "world news", "global", "foreign", "trump", "biden"],
        "trending_terms": ["충격", "긴급", "속보", "전쟁", "갈등"]
    },
    "domestic": {
        "name": "국내 이슈",
        "keywords": ["사건", "사고", "사회", "이슈", "논란", "연예인", "스포츠"],
        "search_terms": ["korea news", "domestic", "social issue", "korean society"],
        "trending_terms": ["충격", "논란", "사건", "발생", "체포"]
    },
    "technology": {
        "name": "기술·IT",
        "keywords": ["AI", "인공지능", "기술", "IT", "스마트폰", "메타버스", "애플", "삼성", "테슬라"],
        "search_terms": ["technology", "AI", "tech news", "innovation", "apple", "samsung"],
        "trending_terms": ["혁신", "출시", "공개", "발표", "신제품"]
    },
    "entertainment": {
        "name": "연예·스포츠",
        "keywords": ["연예인", "아이돌", "드라마", "영화", "스포츠", "축구", "야구", "K팝"],
        "search_terms": ["kpop", "korean drama", "entertainment", "sports", "celebrity"],
        "trending_terms": ["데뷔", "컴백", "열애", "결혼", "승리"]
    }
}

# 요청 모델들
class NewsRequest(BaseModel):
    category: str
    max_articles: int = 5
    language: str = "ko"
    auto_post: bool = False

class ReelsRequest(BaseModel):
    news_id: int
    video_style: str = "trending"
    duration: int = 15
    voice_speed: float = 1.2
    include_captions: bool = True
    background_music: bool = True

class NewsPostRequest(BaseModel):
    news_id: int
    caption_style: str = "viral"
    include_hashtags: bool = True
    scheduled_time: Optional[str] = None

class MultiImagePostRequest(BaseModel):
    caption: str
    selected_images: List[str]
    hashtags: List[str]


# 뉴스 수집 시스템 수정 - 중복 필터링 완화 및 디버깅 강화

class AdvancedNewsScrapingSystem:
    def __init__(self):
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    async def _get_session(self):
        """aiohttp 세션 lazy 초기화"""
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(ssl=False)  # SSL 검증 비활성화
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self.session
    
    def _generate_title_hash(self, title: str) -> str:
        """제목 해시 생성 (중복 검사용)"""
        cleaned_title = re.sub(r'[^\w\s]', '', title.lower())
        cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
        return hashlib.md5(cleaned_title.encode('utf-8')).hexdigest()
    
    def _is_duplicate_news(self, title: str, category: str) -> bool:
        """중복 뉴스 검사 (시간 범위 축소)"""
        try:
            title_hash = self._generate_title_hash(title)
            
            conn = sqlite3.connect("news_automation.db")
            cursor = conn.cursor()
            
            # 중복 검사 시간을 6시간으로 축소 (24시간 → 6시간)
            cursor.execute("""
                SELECT COUNT(*) FROM news_articles 
                WHERE title_hash = ? AND category = ? 
                AND datetime(scraped_at) > datetime('now', '-6 hours')
            """, (title_hash, category))
            
            count = cursor.fetchone()[0]
            conn.close()
            
            return count > 0
            
        except Exception as e:
            logger.error(f"중복 검사 오류: {e}")
            return False  # 오류 시 중복이 아니라고 판단
    
    async def scrape_latest_news(self, category: str, max_articles: int = 10) -> List[Dict]:
        """최신 뉴스 크롤링 - 디버깅 강화"""
        try:
            logger.info(f"🔍 {category} 카테고리 뉴스 수집 시작")
            all_news = []
            
            # Google News 크롤링
            google_news = await self._scrape_google_news(category, max_articles)
            logger.info(f"📰 Google News에서 {len(google_news)}개 뉴스 수집")
            all_news.extend(google_news)
            
            if not all_news:
                logger.warning(f"❌ {category}: 원본 뉴스 수집 실패")
                # 테스트용 더미 뉴스 생성
                return self._create_dummy_news(category, max_articles)
            
            # 중복 제거 (더 관대하게)
            unique_news = self._filter_duplicate_news(all_news, relaxed=True)
            logger.info(f"🔄 중복 제거 후: {len(unique_news)}개")
            
            if not unique_news:
                logger.warning(f"⚠️ {category}: 중복 제거 후 뉴스 없음 - 강제로 최신 뉴스 사용")
                # 중복 검사 무시하고 최신 뉴스 반환
                if all_news:
                    return all_news[:max_articles]
                else:
                    return self._create_dummy_news(category, max_articles)
            
            # 바이럴 점수 기반 정렬
            sorted_news = sorted(unique_news, key=lambda x: x['viral_score'], reverse=True)
            
            result = sorted_news[:max_articles]
            logger.info(f"✅ {category}: 최종 {len(result)}개 뉴스 반환")
            return result
            
        except Exception as e:
            logger.error(f"❌ 뉴스 크롤링 오류: {e}")
            # 오류 시 더미 뉴스 반환
            return self._create_dummy_news(category, max_articles)
    
    def _create_dummy_news(self, category: str, max_articles: int) -> List[Dict]:
        """테스트용 더미 뉴스 생성"""
        logger.info(f"🤖 {category} 카테고리 더미 뉴스 생성")
        
        category_info = NEWS_CATEGORIES.get(category, NEWS_CATEGORIES["technology"])
        dummy_titles = {
            "technology": [
                "AI 기술의 놀라운 발전, 새로운 혁신 등장",
                "스마트폰 시장에 충격적인 변화 예고",
                "테크 기업들의 최신 동향과 전망"
            ],
            "stock": [
                "주식시장 급등, 투자자들 주목",
                "경제 전문가들이 예측하는 시장 동향",
                "코스피 상승세, 주요 종목 분석"
            ],
            "domestic": [
                "국내 주요 이슈 속보 전해져",
                "사회 전반에 걸친 새로운 변화",
                "국민들이 관심 갖는 최신 소식"
            ]
        }
        
        titles = dummy_titles.get(category, ["최신 뉴스 속보", "주요 이슈 업데이트", "사회 동향 분석"])
        
        dummy_news = []
        current_time = datetime.now().isoformat()
        
        for i in range(min(max_articles, len(titles))):
            title = f"{titles[i]} ({datetime.now().strftime('%H:%M')})"
            news_item = {
                "title": title,
                "title_hash": self._generate_title_hash(title),
                "link": f"https://example.com/news/{category}/{i+1}",
                "summary": f"{category_info['name']} 관련 중요 소식입니다. {title}",
                "source": "뉴스 자동 생성",
                "category": category,
                "keywords": category_info["keywords"],
                "viral_score": round(2.0 + i * 0.5, 2),  # 다양한 점수
                "scraped_at": current_time
            }
            dummy_news.append(news_item)
        
        logger.info(f"✅ {len(dummy_news)}개 더미 뉴스 생성 완료")
        return dummy_news
    
    async def _scrape_google_news(self, category: str, max_articles: int) -> List[Dict]:
        """Google News RSS 크롤링 - 오류 처리 강화"""
        try:
            category_info = NEWS_CATEGORIES.get(category, NEWS_CATEGORIES["domestic"])
            news_list = []
            
            session = await self._get_session()
            
            # 검색어 다양화
            search_terms = category_info["search_terms"][:2]
            if category == "technology":
                search_terms = ["technology", "AI", "tech news"]
            elif category == "stock":
                search_terms = ["stock market", "finance", "economy"]
            
            logger.info(f"🔍 검색어: {search_terms}")
            
            for search_term in search_terms:
                try:
                    encoded_term = urllib.parse.quote(search_term)
                    rss_url = f"https://news.google.com/rss/search?q={encoded_term}&hl=ko&gl=KR&ceid=KR:ko"
                    
                    logger.info(f"📡 RSS 요청: {rss_url}")
                    
                    async with session.get(rss_url, headers=self.headers) as response:
                        logger.info(f"📡 응답 코드: {response.status}")
                        
                        if response.status == 200:
                            content = await response.text()
                            logger.info(f"📄 응답 길이: {len(content)} 문자")
                            
                            if len(content) < 100:
                                logger.warning(f"⚠️ 응답이 너무 짧음: {content[:100]}")
                                continue
                            
                            feed = feedparser.parse(content)
                            logger.info(f"📰 파싱된 엔트리 수: {len(feed.entries)}")
                            
                            if not feed.entries:
                                logger.warning(f"⚠️ '{search_term}': RSS 엔트리 없음")
                                continue
                            
                            for entry in feed.entries[:max_articles//2]:
                                try:
                                    title = entry.title
                                    if ' - ' in title:
                                        title = title.split(' - ')[0]
                                    
                                    news_item = {
                                        "title": title.strip(),
                                        "link": entry.link,
                                        "published": entry.get('published', ''),
                                        "summary": entry.get('summary', title),
                                        "source": "Google News",
                                        "category": category,
                                        "keywords": category_info["keywords"],
                                        "viral_score": self._calculate_viral_score(title),
                                        "scraped_at": datetime.now().isoformat()
                                    }
                                    news_list.append(news_item)
                                    logger.info(f"✅ 뉴스 추가: {title[:50]}...")
                                    
                                except Exception as entry_error:
                                    logger.warning(f"⚠️ 엔트리 처리 오류: {entry_error}")
                                    continue
                                    
                        else:
                            logger.warning(f"⚠️ HTTP {response.status}: {search_term}")
                            
                except Exception as term_error:
                    logger.warning(f"⚠️ 검색어 '{search_term}' 오류: {term_error}")
                    continue
            
            logger.info(f"📊 총 수집된 뉴스: {len(news_list)}개")
            return news_list
            
        except Exception as e:
            logger.error(f"❌ Google News 크롤링 오류: {e}")
            return []
    
    def _filter_duplicate_news(self, news_list: List[Dict], relaxed: bool = False) -> List[Dict]:
        """중복 뉴스 필터링 - 관대한 모드 추가"""
        unique_news = []
        seen_hashes = set()
        
        for news in news_list:
            title_hash = self._generate_title_hash(news['title'])
            
            # 현재 세션에서 중복 확인
            if title_hash in seen_hashes:
                logger.info(f"🔄 세션 중복 제외: {news['title'][:30]}...")
                continue
            
            # DB 중복 확인 (relaxed 모드에서는 스킵)
            if not relaxed and self._is_duplicate_news(news['title'], news['category']):
                logger.info(f"🔄 DB 중복 제외: {news['title'][:30]}...")
                continue
            
            seen_hashes.add(title_hash)
            news['title_hash'] = title_hash
            unique_news.append(news)
            logger.info(f"✅ 유니크 뉴스: {news['title'][:30]}...")
        
        logger.info(f"🔄 중복 제거 결과: {len(news_list)} → {len(unique_news)}")
        return unique_news
    
    def _calculate_viral_score(self, title: str) -> float:
        """바이럴 점수 계산"""
        score = 1.0
        title_lower = title.lower()
        
        # 자극적인 키워드
        viral_keywords = [
            "긴급", "속보", "충격", "논란", "폭등", "폭락", "급등", "급락", 
            "사상최고", "사상최저", "역대최대", "파격", "깜짝", "반전",
            "breaking", "urgent", "shock", "surge", "plunge", "exclusive"
        ]
        for keyword in viral_keywords:
            if keyword in title_lower:
                score += 2.0
        
        # 숫자/퍼센트 포함
        if re.search(r'\d+%|\d+억|\d+만|\d+\$|\d+배', title):
            score += 1.5
        
        # 의문문/느낌표
        if '?' in title or '!' in title:
            score += 1.0
        
        # 제목 길이 적절성
        if 15 <= len(title) <= 60:
            score += 1.0
        
        return round(score, 2)
    
    async def close(self):
        """세션 종료"""
        if self.session and not self.session.closed:
            await self.session.close()


# 릴스 제작 시스템
class ReelsProductionSystem:
    def __init__(self):
        self.temp_dir = TEMP_DIR
        self.output_dir = VIDEO_OUTPUT_DIR
        self.audio_dir = AUDIO_OUTPUT_DIR
    
    async def create_news_reel(self, news_data: Dict, style: str = "trending", duration: int = 15) -> Dict:
        """뉴스 릴스 제작"""
        try:
            logger.info(f"📹 릴스 제작 시작: {news_data['title'][:50]}...")
            
            # 1단계: TTS 음성 생성
            audio_result = await self._generate_tts_audio(news_data, duration)
            if not audio_result["success"]:
                return audio_result
            
            # 2단계: 비주얼 생성
            visual_result = await self._create_visual_content(news_data, style, duration)
            if not visual_result["success"]:
                return visual_result
            
            # 3단계: 최종 비디오 (간단 버전)
            final_result = await self._create_simple_video(
                visual_result["visual_path"],
                news_data,
                duration
            )
            
            return final_result
            
        except Exception as e:
            logger.error(f"릴스 제작 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "릴스 제작 중 오류가 발생했습니다."
            }
    
    async def _generate_tts_audio(self, news_data: Dict, duration: int) -> Dict:
        """TTS 음성 생성"""
        try:
            script = self._create_news_script(news_data, duration)
            
            # gTTS로 음성 생성
            tts = gtts.gTTS(text=script, lang='ko', slow=False)
            
            audio_filename = f"news_{news_data['id']}_{int(time.time())}.mp3"
            audio_path = os.path.join(self.audio_dir, audio_filename)
            
            tts.save(audio_path)
            
            logger.info(f"✅ TTS 음성 생성 완료: {audio_path}")
            
            return {
                "success": True,
                "audio_path": audio_path,
                "script": script,
                "duration": duration
            }
            
        except Exception as e:
            logger.error(f"TTS 생성 오류: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _create_news_script(self, news_data: Dict, duration: int) -> str:
        """뉴스 스크립트 생성"""
        title = news_data['title']
        category = NEWS_CATEGORIES.get(news_data['category'], {}).get('name', '뉴스')
        
        if duration <= 15:
            script = f"{category} 속보입니다. {title}. 이 소식에 대한 여러분의 생각은 어떠신가요?"
        elif duration <= 30:
            summary = news_data.get('summary', title)[:100]
            script = f"{category} 긴급 뉴스를 전해드립니다. {title}. {summary}."
        else:
            summary = news_data.get('summary', title)
            script = f"안녕하세요. {category} 속보를 전해드립니다. {title}. {summary}."
        
        # 목표 길이에 맞게 조정
        target_chars = int(duration * 2.5)
        if len(script) > target_chars:
            script = script[:target_chars-3] + "..."
        
        return script
    
    async def _create_visual_content(self, news_data: Dict, style: str, duration: int) -> Dict:
        """비주얼 콘텐츠 생성"""
        try:
            visual_path = await self._create_simple_visual(news_data, duration)
            
            return {
                "success": True,
                "visual_path": visual_path,
                "style": style
            }
            
        except Exception as e:
            logger.error(f"비주얼 생성 오류: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _create_simple_visual(self, news_data: Dict, duration: int) -> str:
        """간단한 비주얼 생성"""
        try:
            # 9:16 비율 (1080x1920)
            width, height = 1080, 1920
            fps = 30
            frames_count = int(duration * fps)
            
            # 기본 배경색과 텍스트
            background_frames = []
            title_lines = self._wrap_text(news_data['title'], 15)
            
            for frame_num in range(frames_count):
                # 단순한 그라데이션 배경
                img = Image.new('RGB', (width, height))
                draw = ImageDraw.Draw(img)
                
                # 그라데이션 효과
                for y in range(height):
                    ratio = y / height
                    r = int(100 + ratio * 155)  # 100에서 255로
                    g = int(50 + ratio * 100)   # 50에서 150으로
                    b = int(200 + ratio * 55)   # 200에서 255로
                    draw.line([(0, y), (width, y)], fill=(r, g, b))
                
                # 제목 텍스트 추가
                try:
                    # 기본 폰트 사용
                    for i, line in enumerate(title_lines[:3]):
                        y_pos = height//2 - 50 + i * 60
                        
                        # 텍스트 그림자
                        draw.text((width//2 + 3, y_pos + 3), line, fill=(0, 0, 0), anchor="mm")
                        # 메인 텍스트
                        draw.text((width//2, y_pos), line, fill=(255, 255, 255), anchor="mm")
                
                except Exception as text_error:
                    logger.warning(f"텍스트 그리기 오류: {text_error}")
                
                # numpy 배열로 변환
                frame_array = np.array(img)
                background_frames.append(frame_array)
            
            # 비디오 파일로 저장
            visual_filename = f"visual_{news_data['id']}_{int(time.time())}.mp4"
            visual_path = os.path.join(self.temp_dir, visual_filename)
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(visual_path, fourcc, fps, (width, height))
            
            for frame in background_frames:
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                out.write(frame_bgr)
            
            out.release()
            
            logger.info(f"✅ 비주얼 생성 완료: {visual_path}")
            return visual_path
            
        except Exception as e:
            logger.error(f"비주얼 생성 오류: {e}")
            raise
    
    def _wrap_text(self, text: str, max_chars: int) -> List[str]:
        """텍스트를 여러 줄로 분할"""
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            if len(current_line + " " + word) <= max_chars:
                current_line += " " + word if current_line else word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        return lines
    
    async def _create_simple_video(self, visual_path: str, news_data: Dict, duration: int) -> Dict:
        """간단한 비디오 생성"""
        try:
            # 파일 크기 확인
            file_size = os.path.getsize(visual_path) / (1024 * 1024)  # MB
            
            # 최종 출력 디렉토리로 복사
            output_filename = f"reel_{news_data['id']}_{int(time.time())}.mp4"
            output_path = os.path.join(self.output_dir, output_filename)
            
            shutil.copy2(visual_path, output_path)
            
            logger.info(f"🎬 릴스 제작 완료: {output_path} ({file_size:.1f}MB)")
            
            return {
                "success": True,
                "video_path": output_path,
                "file_size_mb": round(file_size, 1),
                "duration": duration,
                "message": f"릴스가 성공적으로 제작되었습니다! ({file_size:.1f}MB)"
            }
            
        except Exception as e:
            logger.error(f"비디오 생성 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "비디오 생성 중 오류가 발생했습니다."
            }

# AI 콘텐츠 생성 시스템
class AdvancedContentGenerator:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        
        if not api_key:
            logger.warning("⚠️ OPENAI_API_KEY가 설정되지 않았습니다. AI 기능이 제한됩니다.")
            self.openai_client = None
            return
        
        try:
            if OPENAI_V1:
                self.openai_client = openai.OpenAI(api_key=api_key)
            else:
                openai.api_key = api_key
                self.openai_client = openai
            
            logger.info(f"✅ OpenAI 클라이언트 초기화 완료 (v{openai.__version__})")
            
        except Exception as e:
            logger.error(f"OpenAI 클라이언트 초기화 오류: {e}")
            self.openai_client = None
    
    async def generate_viral_caption(self, news_data: Dict, style: str = "viral") -> Dict:
        """바이럴 캡션 생성"""
        
        if not self.openai_client:
            return self._generate_fallback_caption(news_data)
        
        prompt = f"""
다음 뉴스를 바탕으로 인스타그램 릴스용 캡션을 작성해주세요.

뉴스 제목: {news_data['title']}
카테고리: {news_data['category']}

요구사항:
1. 첫 줄에 시선을 사로잡는 훅 문장
2. 이모지 2-3개 사용
3. 2-3줄의 간결한 구성
4. 댓글 유도 질문 포함

캡션만 답변하세요:
"""
        
        try:
            if OPENAI_V1:
                response = self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "당신은 SNS 마케터입니다."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=200,
                    temperature=0.9
                )
                caption = response.choices[0].message.content.strip()
            else:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "당신은 SNS 마케터입니다."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=200,
                    temperature=0.9
                )
                caption = response.choices[0].message.content.strip()
            
            return {
                'caption': caption,
                'style': style,
                'estimated_engagement': 'high'
            }
            
        except Exception as e:
            logger.error(f"바이럴 캡션 생성 오류: {e}")
            return self._generate_fallback_caption(news_data)
    
    async def generate_trending_hashtags(self, news_data: Dict) -> List[str]:
        """트렌딩 해시태그 생성"""
        
        if not self.openai_client:
            return self._get_category_hashtags(news_data['category'])
        
        # 기본 해시태그 반환 (안전)
        return self._get_category_hashtags(news_data['category'])
    
    def _get_category_hashtags(self, category: str) -> List[str]:
        """카테고리별 기본 해시태그"""
        hashtags_map = {
            "stock": ["#주식", "#투자", "#경제", "#코스피", "#증시", "#재테크"],
            "politics": ["#정치", "#뉴스", "#속보", "#정부", "#대통령", "#시사"],
            "international": ["#해외뉴스", "#국제", "#글로벌", "#외신", "#세계뉴스"],
            "domestic": ["#국내뉴스", "#사회", "#이슈", "#한국", "#속보"],
            "technology": ["#기술", "#IT", "#테크", "#혁신", "#AI", "#스마트폰"],
            "entertainment": ["#연예", "#스포츠", "#케이팝", "#드라마", "#연예인"]
        }
        
        base_tags = hashtags_map.get(category, ["#뉴스", "#이슈"])
        common_tags = ["#트렌드", "#화제", "#팔로우", "#좋아요"]
        
        return base_tags + common_tags
    
    def _generate_fallback_caption(self, news_data: Dict) -> Dict:
        """폴백 캡션 생성"""
        title = news_data['title']
        
        hooks = [
            "🚨 긴급 속보!",
            "😱 이거 실화인가요?",
            "🔥 지금 화제!",
            "⚡ 방금 터진 소식!"
        ]
        
        hook = random.choice(hooks)
        
        return {
            'caption': f"{hook}\n\n{title}\n\n여러분 생각은? 👇",
            'style': 'viral'
        }

# Instagram 서비스 클래스
# Instagram 서비스 클래스 - 시뮬레이션 제거 버전
class AdvancedInstagramService:
    def __init__(self):
        self.access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN')
        self.business_account_id = os.getenv('INSTAGRAM_BUSINESS_ACCOUNT_ID')
        self.base_url = "https://graph.facebook.com"
        self.api_version = "v18.0"
        
    def validate_credentials(self) -> bool:
        """인증 정보 유효성 검사"""
        return bool(self.access_token and self.business_account_id)
    
    async def test_connection(self) -> Dict:
        """Instagram 연결 테스트"""
        if not self.validate_credentials():
            return {
                "success": False,
                "error": "Instagram 인증 정보가 설정되지 않았습니다",
                "details": {
                    "access_token": bool(self.access_token),
                    "business_id": bool(self.business_account_id)
                }
            }
        
        try:
            url = f"{self.base_url}/{self.api_version}/{self.business_account_id}"
            params = {
                'fields': 'id,name,username,followers_count',
                'access_token': self.access_token
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "account_info": data,
                    "message": f"✅ Instagram 연결 성공: @{data.get('username', 'N/A')}"
                }
            else:
                error_data = response.json()
                return {
                    "success": False,
                    "error": f"Instagram API 오류 (코드: {response.status_code})",
                    "details": error_data
                }
                
        except Exception as e:
            logger.error(f"Instagram 연결 테스트 오류: {e}")
            return {
                "success": False,
                "error": f"연결 테스트 실패: {str(e)}"
            }
    
    async def post_reel_with_video(self, caption: str, video_url: str) -> Dict:
        """릴스 업로드 (실제 Instagram API 사용)"""
        try:
            if not self.validate_credentials():
                return {
                    "success": False,
                    "error": "Instagram 인증 정보가 설정되지 않았습니다",
                    "message": "Instagram 설정을 확인해주세요"
                }
            
            logger.info(f"🎬 Instagram 릴스 업로드 시작")
            logger.info(f"  비디오: {video_url}")
            logger.info(f"  캡션: {caption[:100]}...")
            
            # 1단계: 릴스 컨테이너 생성
            container_result = await self._create_reel_container(video_url, caption)
            
            if not container_result or not container_result.get("success"):
                return {
                    "success": False,
                    "step": "container_creation",
                    "error": container_result.get("error") if container_result else "컨테이너 생성 실패",
                    "message": "릴스 컨테이너 생성에 실패했습니다."
                }
            
            container_id = container_result["container_id"]
            logger.info(f"✅ 릴스 컨테이너 생성 완료: {container_id}")
            
            # 2단계: 처리 대기 (릴스는 처리 시간이 더 필요)
            logger.info("⏳ 릴스 처리 대기 (10초)...")
            await asyncio.sleep(10)
            
            # 3단계: 릴스 발행
            publish_result = await self.publish_media(container_id)
            
            if publish_result.get("success"):
                logger.info(f"🎉 Instagram 릴스 업로드 완료!")
                return {
                    "success": True,
                    "container_id": container_id,
                    "post_id": publish_result.get("post_id"),
                    "instagram_url": publish_result.get("instagram_url"),
                    "message": "Instagram 릴스가 성공적으로 업로드되었습니다!",
                    "post_type": "reel"
                }
            else:
                return {
                    "success": False,
                    "step": "media_publish",
                    "container_id": container_id,
                    "error": publish_result.get("error"),
                    "message": f"릴스 발행에 실패했습니다: {publish_result.get('message', '알 수 없는 오류')}"
                }
                
        except Exception as e:
            logger.error(f"❌ Instagram 릴스 업로드 오류: {e}")
            return {
                "success": False,
                "step": "general",
                "error": str(e),
                "message": f"Instagram 릴스 업로드 중 오류가 발생했습니다: {str(e)}"
            }
    
    async def _create_reel_container(self, video_url: str, caption: str) -> Optional[Dict]:
        """릴스 컨테이너 생성"""
        if not self.validate_credentials():
            return None
            
        url = f"{self.base_url}/{self.api_version}/{self.business_account_id}/media"
        
        logger.info(f"📱 Instagram 릴스 컨테이너 생성:")
        logger.info(f"  - URL: {url}")
        logger.info(f"  - Video URL: {video_url}")
        logger.info(f"  - Caption 길이: {len(caption)}자")
        
        params = {
            'video_url': video_url,
            'media_type': 'REELS',  # 릴스 타입 지정
            'caption': caption[:2200],  # Instagram 캡션 길이 제한
            'access_token': self.access_token
        }
        
        try:
            response = requests.post(url, data=params, timeout=30)
            
            logger.info(f"릴스 컨테이너 응답 코드: {response.status_code}")
            logger.info(f"릴스 컨테이너 응답: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                container_id = data.get('id')
                logger.info(f"✅ 릴스 컨테이너 생성 성공: {container_id}")
                
                return {
                    "success": True,
                    "container_id": container_id,
                    "response": data
                }
            else:
                error_data = response.json()
                logger.error(f"❌ 릴스 컨테이너 생성 실패: {error_data}")
                
                return {
                    "success": False,
                    "error": error_data,
                    "status_code": response.status_code
                }
                
        except Exception as e:
            logger.error(f"❌ 릴스 컨테이너 생성 오류: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def publish_media(self, creation_id: str) -> Dict:
        """미디어 발행 (이미지/릴스 공통)"""
        if not self.validate_credentials():
            return {"success": False, "error": "인증 정보 없음"}
            
        url = f"{self.base_url}/{self.api_version}/{self.business_account_id}/media_publish"
        
        params = {
            'creation_id': creation_id,
            'access_token': self.access_token
        }
        
        try:
            logger.info(f"📤 Instagram 미디어 발행 시작: {creation_id}")
            
            response = requests.post(url, data=params, timeout=30)
            
            logger.info(f"미디어 발행 응답 코드: {response.status_code}")
            logger.info(f"미디어 발행 응답: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                post_id = data.get('id')
                logger.info(f"🎉 Instagram 발행 성공! Post ID: {post_id}")
                
                return {
                    "success": True,
                    "post_id": post_id,
                    "message": f"Instagram 발행 성공! ID: {post_id}",
                    "instagram_url": f"https://www.instagram.com/p/{post_id}/" if post_id else None
                }
            else:
                error_data = response.json()
                logger.error(f"❌ 미디어 발행 실패: {error_data}")
                
                return {
                    "success": False,
                    "error": error_data,
                    "status_code": response.status_code,
                    "message": f"Instagram 발행 실패: {error_data.get('error', {}).get('message', '알 수 없는 오류')}"
                }
                
        except Exception as e:
            logger.error(f"❌ 미디어 발행 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Instagram 발행 오류: {str(e)}"
            }

# 데이터베이스 초기화
def init_enhanced_db():
    """데이터베이스 초기화"""
    try:
        conn = sqlite3.connect("news_automation.db")
        cursor = conn.cursor()
        
        # 뉴스 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                title_hash TEXT,
                link TEXT,
                summary TEXT,
                content TEXT,
                source TEXT,
                category TEXT,
                keywords TEXT,
                viral_score REAL,
                scraped_at TEXT,
                published_at TEXT,
                is_processed BOOLEAN DEFAULT FALSE,
                view_count INTEGER DEFAULT 0
            )
        """)
        
        # 릴스 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_reels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER,
                video_path TEXT,
                audio_path TEXT,
                script TEXT,
                style TEXT,
                duration INTEGER,
                file_size_mb REAL,
                created_at TEXT,
                status TEXT DEFAULT 'created',
                view_count INTEGER DEFAULT 0,
                like_count INTEGER DEFAULT 0,
                FOREIGN KEY (news_id) REFERENCES news_articles (id)
            )
        """)
        
        # 콘텐츠 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generated_news_content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER,
                caption TEXT,
                hashtags TEXT,
                script_data TEXT,
                style TEXT,
                estimated_engagement TEXT,
                created_at TEXT,
                FOREIGN KEY (news_id) REFERENCES news_articles (id)
            )
        """)
        
        # 포스팅 기록 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER,
                content_id INTEGER,
                reel_id INTEGER,
                platform TEXT,
                post_type TEXT DEFAULT 'image',
                post_id TEXT,
                caption TEXT,
                hashtags TEXT,
                media_urls TEXT,
                posted_at TEXT,
                status TEXT DEFAULT 'pending',
                engagement_stats TEXT,
                error_message TEXT,
                instagram_url TEXT,
                reach_count INTEGER DEFAULT 0,
                impression_count INTEGER DEFAULT 0,
                FOREIGN KEY (news_id) REFERENCES news_articles (id),
                FOREIGN KEY (content_id) REFERENCES generated_news_content (id),
                FOREIGN KEY (reel_id) REFERENCES news_reels (id)
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("✅ 데이터베이스 초기화 완료")
        return True
    except Exception as e:
        logger.error(f"❌ DB 초기화 오류: {e}")
        return False

# FastAPI 앱 초기화
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ADVANCED NEWS AUTOMATION 시작")
    
    try:
        init_enhanced_db()
    except Exception as e:
        logger.error(f"DB 초기화 실패: {e}")
    
    yield
    
    try:
        if hasattr(app.state, 'news_scraper'):
            await app.state.news_scraper.close()
    except Exception as e:
        logger.error(f"세션 정리 오류: {e}")

app = FastAPI(
    title="ADVANCED NEWS AUTOMATION", 
    description="AI 뉴스 수집 + 릴스 제작 + 인스타그램 자동 업로드",
    version="2.0.0",
    lifespan=lifespan, 
    debug=DEBUG
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙 (안전)
try:
    app.mount("/generated_videos", StaticFiles(directory=VIDEO_OUTPUT_DIR), name="videos")
    app.mount("/generated_audio", StaticFiles(directory=AUDIO_OUTPUT_DIR), name="audio")
    logger.info(f"✅ 정적 파일 마운트 완료")
except Exception as e:
    logger.warning(f"⚠️ 정적 파일 마운트 실패: {e}")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

# 서비스 인스턴스 (글로벌)
_news_scraper = None
_content_generator = None
_instagram_service = None
_reels_producer = None

def get_news_scraper():
    global _news_scraper
    if _news_scraper is None:
        _news_scraper = AdvancedNewsScrapingSystem()
    return _news_scraper

def get_content_generator():
    global _content_generator
    if _content_generator is None:
        _content_generator = AdvancedContentGenerator()
    return _content_generator

def get_instagram_service():
    global _instagram_service
    if _instagram_service is None:
        _instagram_service = AdvancedInstagramService()
    return _instagram_service

def get_reels_producer():
    global _reels_producer
    if _reels_producer is None:
        _reels_producer = ReelsProductionSystem()
    return _reels_producer

# API 라우트들

@app.get("/")
async def home():
    """홈페이지"""
    return {
        "title": "🎬 ADVANCED NEWS AUTOMATION",
        "description": "AI 뉴스 수집 + 릴스 제작 + 인스타그램 자동화",
        "features": [
            "🔍 다중 소스 뉴스 크롤링 (Google News)",
            "🤖 AI 바이럴 캡션 생성",
            "🎬 자동 릴스 제작 (TTS + 비주얼)",
            "📱 인스타그램 자동 업로드",
            "📊 참여도 분석 및 최적화"
        ],
        "endpoints": {
            "dashboard": "/dashboard",
            "api_docs": "/docs",
            "health": "/health"
        }
    }

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """대시보드 페이지"""
    return get_default_dashboard_html()

def get_default_dashboard_html():
    """기본 대시보드 HTML"""
    return """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎬 NEWS AUTOMATION</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            min-height: 100vh;
        }
        .container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            margin-top: 20px;
            padding: 40px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        }
        .card {
            border: none;
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s ease;
        }
        .card:hover {
            transform: translateY(-5px);
        }
        .btn-primary {
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            border: none;
            border-radius: 10px;
        }
        .btn-success {
            background: linear-gradient(135deg, #10b981, #06b6d4);
            border: none;
            border-radius: 10px;
        }
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }
        .status-online { background: #10b981; }
        .status-offline { background: #ef4444; }
        .log-terminal {
            background: #1a1a1a;
            color: #00ff00;
            border-radius: 12px;
            padding: 20px;
            font-family: 'Monaco', 'Consolas', monospace;
            font-size: 14px;
            height: 200px;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="text-center mb-5">
            <h1 class="display-4 fw-bold">
                <i class="fas fa-robot text-primary me-3"></i>
                NEWS AUTOMATION
            </h1>
            <p class="lead text-muted">AI 뉴스 수집 + 릴스 제작 + Instagram 자동화</p>
            <div class="mt-3">
                <span id="statusDot" class="status-dot status-online"></span>
                <span id="statusText" class="fw-semibold">시스템 준비 완료</span>
            </div>
        </div>

        <div class="row g-4">
            <!-- 시스템 상태 -->
            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-body text-center">
                        <i class="fas fa-heartbeat fa-3x text-primary mb-3"></i>
                        <h5 class="card-title">📊 시스템 상태</h5>
                        <p class="card-text text-muted">서버 상태 및 기본 정보를 확인합니다</p>
                        <button class="btn btn-primary w-100" onclick="checkHealth()">
                            <i class="fas fa-check-circle me-2"></i>상태 확인
                        </button>
                        <div id="status" class="mt-3"></div>
                    </div>
                </div>
            </div>

            <!-- 뉴스 수집 -->
            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-body text-center">
                        <i class="fas fa-newspaper fa-3x text-success mb-3"></i>
                        <h5 class="card-title">📰 뉴스 수집</h5>
                        <p class="card-text text-muted">최신 기술 뉴스를 자동으로 수집합니다</p>
                        <button class="btn btn-success w-100" onclick="scrapeNews()">
                            <i class="fas fa-download me-2"></i>뉴스 수집 시작
                        </button>
                        <div id="news-result" class="mt-3"></div>
                    </div>
                </div>
            </div>

            <!-- 전체 자동화 -->
            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-body text-center">
                        <i class="fas fa-rocket fa-3x text-warning mb-3"></i>
                        <h5 class="card-title">🚀 전체 자동화</h5>
                        <p class="card-text text-muted">뉴스 수집부터 릴스 제작까지 한번에</p>
                        <button class="btn btn-warning w-100" onclick="runFullAutomation()">
                            <i class="fas fa-play me-2"></i>자동화 실행
                        </button>
                        <div id="automation-result" class="mt-3"></div>
                    </div>
                </div>
            </div>

            <!-- API 문서 -->
            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-body text-center">
                        <i class="fas fa-book fa-3x text-info mb-3"></i>
                        <h5 class="card-title">📚 API 문서</h5>
                        <p class="card-text text-muted">전체 API 기능을 확인하고 테스트합니다</p>
                        <a href="/docs" class="btn btn-info w-100" target="_blank">
                            <i class="fas fa-external-link-alt me-2"></i>API 문서 열기
                        </a>
                    </div>
                </div>
            </div>
        </div>

        <!-- 시스템 로그 -->
        <div class="row mt-5">
            <div class="col-12">
                <div class="card">
                    <div class="card-header bg-dark text-white">
                        <h5 class="mb-0">
                            <i class="fas fa-terminal me-2"></i>시스템 로그
                        </h5>
                    </div>
                    <div class="card-body p-0">
                        <div id="logContainer" class="log-terminal">
[시스템] NEWS AUTOMATION 서버 시작됨
[정보] 시스템 초기화 완료. 명령을 기다리는 중...

</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // 로그 추가 함수
        function addLog(message, type = 'info') {
            const container = document.getElementById('logContainer');
            const timestamp = new Date().toLocaleTimeString();
            
            let icon = 'ℹ️';
            let color = '#00ff00';
            
            if (type === 'error') {
                icon = '❌';
                color = '#ff4444';
            } else if (type === 'success') {
                icon = '✅';
                color = '#00ff88';
            } else if (type === 'warning') {
                icon = '⚠️';
                color = '#ffaa00';
            }
            
            container.innerHTML += `<span style="color: ${color}">[${timestamp}] ${icon} ${message}</span><br>`;
            container.scrollTop = container.scrollHeight;
        }

        // 안전한 API 호출
        async function safeApiCall(url, options = {}) {
            try {
                const response = await fetch(url, {
                    ...options,
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        ...options.headers
                    }
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const responseText = await response.text();
                
                if (!responseText.trim()) {
                    throw new Error('서버에서 빈 응답을 받았습니다');
                }
                
                try {
                    return JSON.parse(responseText);
                } catch (parseError) {
                    throw new Error(`JSON 파싱 실패: ${parseError.message}`);
                }
                
            } catch (error) {
                console.error('API 호출 오류:', error);
                throw error;
            }
        }

        // 시스템 상태 확인
        async function checkHealth() {
            addLog('시스템 상태를 확인하는 중...', 'info');
            
            try {
                const data = await safeApiCall('/health');
                
                document.getElementById('status').innerHTML = 
                    `<div class="alert alert-success alert-sm">
                        <strong>✅ 시스템 정상</strong><br>
                        <small>상태: ${data.status}</small><br>
                        <small>뉴스: ${data.statistics?.total_news || 0}개</small><br>
                        <small>릴스: ${data.statistics?.total_reels || 0}개</small>
                    </div>`;
                
                document.getElementById('statusDot').className = 'status-dot status-online';
                document.getElementById('statusText').textContent = '시스템 정상 작동 중';
                
                addLog('✅ 시스템 상태 확인 완료', 'success');
                
            } catch (error) {
                document.getElementById('status').innerHTML = 
                    `<div class="alert alert-danger alert-sm">
                        <strong>❌ 연결 오류</strong><br>
                        <small>${error.message}</small>
                    </div>`;
                
                document.getElementById('statusDot').className = 'status-dot status-offline';
                document.getElementById('statusText').textContent = '시스템 오류';
                
                addLog(`❌ 시스템 상태 확인 실패: ${error.message}`, 'error');
            }
        }
        
        // 뉴스 수집
        async function scrapeNews() {
            addLog('기술 뉴스 수집을 시작합니다...', 'info');
            
            try {
                const data = await safeApiCall('/api/scrape-news', {
                    method: 'POST',
                    body: JSON.stringify({
                        category: 'technology', 
                        max_articles: 3
                    })
                });
                
                if (data.success) {
                    document.getElementById('news-result').innerHTML = 
                        `<div class="alert alert-success alert-sm">
                            <strong>✅ 수집 완료!</strong><br>
                            <small>${data.message}</small><br>
                            <small>최고 바이럴 점수: ${data.highest_viral_score || 0}</small>
                        </div>`;
                    
                    addLog(`✅ 뉴스 수집 성공: ${data.news?.length || 0}개`, 'success');
                    
                } else {
                    document.getElementById('news-result').innerHTML = 
                        `<div class="alert alert-warning alert-sm">
                            <strong>⚠️ 알림</strong><br>
                            <small>${data.message}</small>
                        </div>`;
                    
                    addLog(`⚠️ 뉴스 수집 결과: ${data.message}`, 'warning');
                }
                
            } catch (error) {
                document.getElementById('news-result').innerHTML = 
                    `<div class="alert alert-danger alert-sm">
                        <strong>❌ 오류 발생</strong><br>
                        <small>${error.message}</small>
                    </div>`;
                
                addLog(`❌ 뉴스 수집 오류: ${error.message}`, 'error');
            }
        }

        // 전체 자동화 실행 함수 - 디버깅 강화
async function runFullAutomation() {
    addLog('🚀 전체 자동화 프로세스를 시작합니다...', 'info');
    
    try {
        const data = await safeApiCall('/api/automation/full-reel-process', {
            method: 'POST'
        });
        
        // 디버그 정보 로깅
        if (data.debug_info && Array.isArray(data.debug_info)) {
            data.debug_info.forEach(info => {
                addLog(`🔍 ${info}`, 'info');
            });
        }
        
        // 오류 정보 로깅
        if (data.results && data.results.errors && Array.isArray(data.results.errors)) {
            data.results.errors.forEach(error => {
                addLog(`❌ ${error}`, 'error');
            });
        }
        
        if (data.success) {
            const results = data.results || {};
            
            document.getElementById('automation-result').innerHTML = 
                `<div class="alert alert-success alert-sm">
                    <strong>✅ 자동화 완료!</strong><br>
                    <small>뉴스 수집: ${results.scraped_news || 0}개</small><br>
                    <small>릴스 제작: ${results.created_reels || 0}개</small><br>
                    <small>Instagram 업로드: ${results.posted_reels || 0}개</small><br>
                    <small>오류: ${(results.errors || []).length}개</small>
                </div>`;
            
            addLog(`✅ 자동화 완료: ${data.message}`, 'success');
            
            // 오류가 있으면 경고 표시
            if (results.errors && results.errors.length > 0) {
                addLog(`⚠️ ${results.errors.length}개의 오류가 발생했습니다`, 'warning');
            }
            
        } else {
            document.getElementById('automation-result').innerHTML = 
                `<div class="alert alert-danger alert-sm">
                    <strong>❌ 자동화 실패</strong><br>
                    <small>${data.error || data.message || '알 수 없는 오류'}</small><br>
                    ${data.debug_summary ? `<small>마지막 단계: ${data.debug_summary.last_step}</small>` : ''}
                </div>`;
            
            addLog(`❌ 자동화 실패: ${data.error || data.message || '알 수 없는 오류'}`, 'error');
            
            // 디버그 요약 정보 표시
            if (data.debug_summary) {
                addLog(`🔍 디버그 정보: ${data.debug_summary.total_steps}단계 실행, ${data.debug_summary.error_count}개 오류`, 'warning');
            }
        }
        
    } catch (error) {
        document.getElementById('automation-result').innerHTML = 
            `<div class="alert alert-danger alert-sm">
                <strong>❌ 네트워크 오류</strong><br>
                <small>${error.message}</small>
            </div>`;
        
        addLog(`❌ 네트워크 오류: ${error.message}`, 'error');
        
        // 추가 디버그 정보
        if (error.message.includes('JSON')) {
            addLog('💡 JSON 파싱 오류 - 서버 응답을 확인하세요', 'warning');
        } else if (error.message.includes('fetch')) {
            addLog('💡 네트워크 연결 오류 - 서버 상태를 확인하세요', 'warning');
        }
    }
}

        // 페이지 로드 시 자동 상태 확인
        document.addEventListener('DOMContentLoaded', function() {
            addLog('🚀 NEWS AUTOMATION 대시보드 로드 완료', 'success');
            
            // 자동으로 시스템 상태 확인
            setTimeout(() => {
                checkHealth();
            }, 1000);
        });

        // 에러 핸들러
        window.addEventListener('error', function(e) {
            addLog(`❌ JavaScript 오류: ${e.message}`, 'error');
        });

        window.addEventListener('unhandledrejection', function(e) {
            addLog(`❌ Promise 오류: ${e.reason}`, 'error');
            e.preventDefault();
        });
    </script>
</body>
</html>
    """

@app.post("/api/scrape-news")
async def scrape_news_api(request: NewsRequest):
    """뉴스 수집 API - 디버깅 강화"""
    try:
        logger.info(f"📰 뉴스 수집 요청: {request.category}, {request.max_articles}개")
        
        scraper = get_news_scraper()
        news_list = await scraper.scrape_latest_news(request.category, request.max_articles)
        
        logger.info(f"📊 수집 결과: {len(news_list)}개 뉴스")
        
        if not news_list:
            return {
                "success": False, 
                "message": "수집된 새로운 뉴스가 없습니다",
                "debug_info": [
                    "Google News RSS 접근 실패 또는",
                    "모든 뉴스가 중복으로 필터링됨",
                    "더미 뉴스 생성도 실패"
                ]
            }
        
        # DB에 저장
        saved_news = []
        try:
            conn = sqlite3.connect("news_automation.db")
            cursor = conn.cursor()
            
            for news in news_list:
                try:
                    cursor.execute("""
                        INSERT INTO news_articles 
                        (title, title_hash, link, summary, source, category, keywords, viral_score, scraped_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        news['title'],
                        news['title_hash'],
                        news['link'],
                        news['summary'],
                        news['source'],
                        news['category'],
                        json.dumps(news['keywords']),
                        news['viral_score'],
                        news['scraped_at']
                    ))
                    
                    news_id = cursor.lastrowid
                    news['id'] = news_id
                    saved_news.append(news)
                    logger.info(f"💾 DB 저장: ID {news_id} - {news['title'][:30]}...")
                    
                except Exception as save_error:
                    logger.error(f"❌ 개별 뉴스 저장 오류: {save_error}")
                    continue
            
            conn.commit()
            conn.close()
            logger.info(f"✅ DB 저장 완료: {len(saved_news)}개")
            
        except Exception as db_error:
            logger.error(f"❌ DB 저장 오류: {db_error}")
            # DB 오류가 있어도 뉴스는 반환
        
        return {
            "success": True,
            "message": f"{len(saved_news)}개의 새로운 뉴스를 수집했습니다",
            "news": saved_news,
            "highest_viral_score": max([n['viral_score'] for n in saved_news]) if saved_news else 0,
            "debug_info": [
                f"원본 수집: {len(news_list)}개",
                f"DB 저장: {len(saved_news)}개",
                f"소스: {', '.join(set([n['source'] for n in news_list]))}"
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ 뉴스 수집 API 오류: {e}")
        return {
            "success": False, 
            "error": str(e), 
            "message": "뉴스 수집 중 오류가 발생했습니다",
            "debug_info": [f"시스템 오류: {str(e)}"]
        }

@app.get("/health")
async def health_check():
    """시스템 상태 확인"""
    try:
        conn = sqlite3.connect("news_automation.db")
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM news_articles")
        total_news = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM news_reels")
        total_reels = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM news_posts WHERE status = 'posted'")
        posted_content = cursor.fetchone()[0]
        
        cursor.execute("SELECT AVG(viral_score) FROM news_articles WHERE datetime(scraped_at) > datetime('now', '-1 days')")
        avg_viral_score = cursor.fetchone()[0] or 0
        
        conn.close()
        
        generator = get_content_generator()
        
        return {
            "status": "healthy",
            "database": "connected",
            "environment": "render" if IS_RENDER else "local",
            "services": {
                "news_scraper": "active",
                "reels_producer": "active", 
                "content_generator": "active",
                "openai_available": generator.openai_client is not None,
                "static_files": os.path.exists(VIDEO_OUTPUT_DIR)
            },
            "statistics": {
                "total_news": total_news,
                "total_reels": total_reels,
                "posted_content": posted_content,
                "avg_viral_score": round(avg_viral_score, 2)
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# 자동화 API 함수 수정 - 더 자세한 오류 정보 포함

@app.post("/api/automation/full-reel-process")
async def full_reel_automation():
    """전체 릴스 자동화 프로세스 - 디버깅 강화"""
    try:
        logger.info("🚀 전체 자동화 프로세스 시작")
        
        results = {
            "scraped_news": 0,
            "created_reels": 0,
            "posted_reels": 0,
            "errors": [],
            "debug_info": []
        }
        
        # 1단계: 기본 환경 체크
        try:
            results["debug_info"].append("환경 체크 시작")
            
            # 디렉토리 존재 확인
            dirs_check = {
                "video_dir": os.path.exists(VIDEO_OUTPUT_DIR),
                "audio_dir": os.path.exists(AUDIO_OUTPUT_DIR),
                "temp_dir": os.path.exists(TEMP_DIR)
            }
            results["debug_info"].append(f"디렉토리 체크: {dirs_check}")
            
            # 데이터베이스 연결 테스트
            conn = sqlite3.connect("news_automation.db")
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM news_articles")
            existing_news = cursor.fetchone()[0]
            conn.close()
            results["debug_info"].append(f"기존 뉴스 개수: {existing_news}")
            
        except Exception as env_error:
            error_msg = f"환경 체크 실패: {str(env_error)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["debug_info"].append(error_msg)
        
        # 2단계: 뉴스 수집
        categories = ["technology", "stock"]  # 카테고리 줄임
        scraper = get_news_scraper()
        
        all_news = []
        
        for category in categories:
            try:
                logger.info(f"📰 {category} 카테고리 뉴스 수집 중...")
                results["debug_info"].append(f"{category} 수집 시작")
                
                news_list = await scraper.scrape_latest_news(category, 2)
                results["debug_info"].append(f"{category} 수집 결과: {len(news_list)}개")
                
                if news_list:
                    # DB에 저장
                    try:
                        conn = sqlite3.connect("news_automation.db")
                        cursor = conn.cursor()
                        
                        for news in news_list:
                            try:
                                cursor.execute("""
                                    INSERT INTO news_articles 
                                    (title, title_hash, link, summary, source, category, keywords, viral_score, scraped_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    news['title'],
                                    news.get('title_hash', ''),
                                    news.get('link', ''),
                                    news.get('summary', news['title']),
                                    news.get('source', 'Google News'),
                                    news['category'],
                                    json.dumps(news.get('keywords', [])),
                                    news.get('viral_score', 1.0),
                                    news.get('scraped_at', datetime.now().isoformat())
                                ))
                                news['id'] = cursor.lastrowid
                                all_news.append(news)
                                results["debug_info"].append(f"뉴스 저장 성공: ID {news['id']}")
                            except Exception as news_save_error:
                                error_msg = f"개별 뉴스 저장 오류: {str(news_save_error)}"
                                logger.error(error_msg)
                                results["errors"].append(error_msg)
                        
                        conn.commit()
                        conn.close()
                        
                        results["scraped_news"] += len(news_list)
                        results["debug_info"].append(f"{category} DB 저장 완료: {len(news_list)}개")
                        
                    except Exception as db_error:
                        error_msg = f"{category} DB 저장 오류: {str(db_error)}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)
                        results["debug_info"].append(error_msg)
                else:
                    results["debug_info"].append(f"{category}: 새로운 뉴스 없음")
                
            except Exception as category_error:
                error_msg = f"{category} 수집 오류: {str(category_error)}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
                results["debug_info"].append(error_msg)
                continue
        
        results["debug_info"].append(f"총 수집된 뉴스: {len(all_news)}개")
        
        if not all_news:
            return {
                "success": False,
                "message": "수집된 뉴스가 없습니다",
                "results": results
            }
        
        # 3단계: 릴스 제작
        try:
            producer = get_reels_producer()
            results["debug_info"].append("릴스 제작 시스템 준비 완료")
            
            # 바이럴 점수 기준 상위 뉴스 선별 (1개만)
            top_viral_news = sorted(all_news, key=lambda x: x.get('viral_score', 1.0), reverse=True)[:1]
            results["debug_info"].append(f"릴스 제작 대상: {len(top_viral_news)}개")
            
            for news in top_viral_news:
                try:
                    logger.info(f"🎬 뉴스 ID {news['id']} 릴스 제작 중...")
                    results["debug_info"].append(f"릴스 제작 시작: {news['title'][:30]}...")
                    
                    # 릴스 제작
                    reel_result = await producer.create_news_reel(news, "trending", 15)
                    results["debug_info"].append(f"릴스 제작 결과: {reel_result.get('success', False)}")
                    
                    if reel_result["success"]:
                        # DB에 릴스 저장
                        try:
                            conn = sqlite3.connect("news_automation.db")
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO news_reels 
                                (news_id, video_path, style, duration, file_size_mb, created_at, status)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                news['id'],
                                reel_result["video_path"],
                                "trending",
                                15,
                                reel_result.get("file_size_mb", 0),
                                datetime.now().isoformat(),
                                'created'
                            ))
                            
                            reel_id = cursor.lastrowid
                            conn.commit()
                            conn.close()
                            
                            results["created_reels"] += 1
                            results["debug_info"].append(f"릴스 DB 저장 완료: ID {reel_id}")
                            
                            # 4단계: Instagram 업로드
                            try:
                                logger.info(f"📱 릴스 ID {reel_id} Instagram 업로드 중...")
                                results["debug_info"].append(f"Instagram 업로드 시작: {reel_id}")
                                
                                # 바이럴 캡션 생성
                                generator = get_content_generator()
                                caption_data = await generator.generate_viral_caption(news, "viral")
                                hashtags = await generator.generate_trending_hashtags(news)
                                full_caption = f"{caption_data['caption']}\n\n{' '.join(hashtags[:10])}"
                                
                                results["debug_info"].append(f"캡션 생성 완료: {len(full_caption)}자")
                                
                                # 비디오 URL 생성
                                video_filename = os.path.basename(reel_result['video_path'])
                                if IS_RENDER:
                                    # Render 환경에서는 실제 도메인 사용
                                    video_url = f"https://your-app.onrender.com/generated_videos/{video_filename}"
                                else:
                                    video_url = f"http://{HOST}:{PORT}/generated_videos/{video_filename}"
                                
                                results["debug_info"].append(f"비디오 URL: {video_url}")
                                
                                # Instagram 업로드
                                instagram = get_instagram_service()
                                
                                # Instagram 연결 상태 먼저 확인
                                connection_test = await instagram.test_connection()
                                results["debug_info"].append(f"Instagram 연결 테스트: {connection_test.get('success', False)}")
                                
                                if not connection_test.get('success'):
                                    error_msg = f"Instagram 연결 실패: {connection_test.get('error', '알 수 없는 오류')}"
                                    results["errors"].append(error_msg)
                                    results["debug_info"].append(error_msg)
                                    continue
                                
                                upload_result = await instagram.post_reel_with_video(full_caption, video_url)
                                results["debug_info"].append(f"Instagram 업로드 결과: {upload_result.get('success', False)}")
                                
                                # 결과 기록
                                try:
                                    conn = sqlite3.connect("news_automation.db")
                                    cursor = conn.cursor()
                                    
                                    status = 'posted' if upload_result.get('success') else 'failed'
                                    error_message = None if upload_result.get('success') else str(upload_result.get('error', ''))
                                    
                                    cursor.execute("""
                                        INSERT INTO news_posts 
                                        (news_id, reel_id, platform, post_type, post_id, caption, hashtags, 
                                         media_urls, posted_at, status, error_message, instagram_url)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (
                                        news['id'],
                                        reel_id,
                                        'instagram',
                                        'reel',
                                        upload_result.get('post_id', ''),
                                        caption_data['caption'],
                                        json.dumps(hashtags),
                                        video_url,
                                        datetime.now().isoformat(),
                                        status,
                                        error_message,
                                        upload_result.get('instagram_url', '')
                                    ))
                                    
                                    conn.commit()
                                    conn.close()
                                    
                                    if upload_result.get('success'):
                                        results["posted_reels"] += 1
                                        results["debug_info"].append(f"Instagram 업로드 성공: {upload_result.get('post_id', '')}")
                                        logger.info(f"✅ 릴스 자동화 성공: {news['title'][:50]}...")
                                    else:
                                        error_msg = f"릴스 업로드 실패: {upload_result.get('message', '알 수 없는 오류')}"
                                        results["errors"].append(error_msg)
                                        results["debug_info"].append(error_msg)
                                
                                except Exception as post_db_error:
                                    error_msg = f"포스팅 기록 저장 오류: {str(post_db_error)}"
                                    logger.error(error_msg)
                                    results["errors"].append(error_msg)
                                    results["debug_info"].append(error_msg)
                            
                            except Exception as instagram_error:
                                error_msg = f"Instagram 업로드 오류: {str(instagram_error)}"
                                logger.error(error_msg)
                                results["errors"].append(error_msg)
                                results["debug_info"].append(error_msg)
                        
                        except Exception as reel_db_error:
                            error_msg = f"릴스 DB 저장 오류: {str(reel_db_error)}"
                            logger.error(error_msg)
                            results["errors"].append(error_msg)
                            results["debug_info"].append(error_msg)
                    
                    else:
                        error_msg = f"릴스 제작 실패: {reel_result.get('message', '알 수 없는 오류')}"
                        results["errors"].append(error_msg)
                        results["debug_info"].append(error_msg)
                
                except Exception as news_process_error:
                    error_msg = f"뉴스 ID {news['id']} 처리 오류: {str(news_process_error)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
                    results["debug_info"].append(error_msg)
                    continue
        
        except Exception as reel_system_error:
            error_msg = f"릴스 시스템 오류: {str(reel_system_error)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["debug_info"].append(error_msg)
        
        # 결과 요약
        success_rate = (results["posted_reels"] / max(results["created_reels"], 1)) * 100
        
        # 성공 여부 판단
        is_success = results["posted_reels"] > 0 or (results["created_reels"] > 0 and len(results["errors"]) == 0)
        
        return {
            "success": is_success,
            "message": f"릴스 자동화 완료 (성공률: {success_rate:.1f}%)",
            "results": results,
            "debug_summary": {
                "total_steps": len(results["debug_info"]),
                "error_count": len(results["errors"]),
                "last_step": results["debug_info"][-1] if results["debug_info"] else "시작 실패"
            }
        }
        
    except Exception as e:
        error_msg = f"전체 자동화 시스템 오류: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False, 
            "error": error_msg,
            "message": "자동화 프로세스 중 시스템 오류가 발생했습니다",
            "debug_info": [error_msg]
        }

@app.get("/api/reels/recent")
async def get_recent_reels(limit: int = 10):
    """최근 제작된 릴스 목록"""
    try:
        conn = sqlite3.connect("news_automation.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nr.*, na.title, na.category
            FROM news_reels nr
            JOIN news_articles na ON nr.news_id = na.id
            ORDER BY nr.created_at DESC 
            LIMIT ?
        """, (limit,))
        
        reels_list = []
        for row in cursor.fetchall():
            reels_list.append({
                'id': row[0],
                'news_id': row[1],
                'video_path': row[2],
                'video_url': f"/generated_videos/{os.path.basename(row[2])}",
                'style': row[4],
                'duration': row[5],
                'file_size_mb': row[6],
                'created_at': row[7],
                'status': row[8],
                'news_title': row[10],
                'category': row[11]
            })
        
        conn.close()
        
        return {
            "success": True,
            "reels": reels_list,
            "total": len(reels_list)
        }
        
    except Exception as e:
        logger.error(f"릴스 목록 조회 오류: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/news/trending")
async def get_trending_news(limit: int = 10):
    """바이럴 점수 기준 트렌딩 뉴스"""
    try:
        conn = sqlite3.connect("news_automation.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, link, summary, source, category, viral_score, scraped_at
            FROM news_articles 
            WHERE datetime(scraped_at) > datetime('now', '-1 days')
            ORDER BY viral_score DESC 
            LIMIT ?
        """, (limit,))
        
        news_list = []
        for row in cursor.fetchall():
            news_list.append({
                'id': row[0],
                'title': row[1],
                'link': row[2],
                'summary': row[3],
                'source': row[4],
                'category': row[5],
                'viral_score': row[6],
                'scraped_at': row[7]
            })
        
        conn.close()
        
        return {
            "success": True,
            "trending_news": news_list,
            "total": len(news_list)
        }
        
    except Exception as e:
        logger.error(f"트렌딩 뉴스 조회 오류: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/create-reel/{news_id}")
async def create_reel_api(news_id: int, request: ReelsRequest):
    """릴스 제작 API"""
    try:
        # 뉴스 데이터 조회
        conn = sqlite3.connect("news_automation.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM news_articles WHERE id = ?", (news_id,))
        news_row = cursor.fetchone()
        
        if not news_row:
            return {"success": False, "message": "뉴스를 찾을 수 없습니다"}
        
        # 뉴스 데이터 구성
        news_data = {
            'id': news_row[0],
            'title': news_row[1],
            'link': news_row[3],
            'summary': news_row[4],
            'source': news_row[6],
            'category': news_row[7],
            'keywords': json.loads(news_row[8]) if news_row[8] else []
        }
        
        # 릴스 제작
        producer = get_reels_producer()
        result = await producer.create_news_reel(
            news_data, 
            request.video_style, 
            request.duration
        )
        
        if result["success"]:
            # DB에 릴스 정보 저장
            cursor.execute("""
                INSERT INTO news_reels 
                (news_id, video_path, style, duration, file_size_mb, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                news_id,
                result["video_path"],
                request.video_style,
                request.duration,
                result["file_size_mb"],
                datetime.now().isoformat(),
                'created'
            ))
            
            reel_id = cursor.lastrowid
            conn.commit()
            
            result["reel_id"] = reel_id
            result["video_url"] = f"/generated_videos/{os.path.basename(result['video_path'])}"
        
        conn.close()
        return result
        
    except Exception as e:
        logger.error(f"릴스 제작 API 오류: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/test-instagram")
async def test_instagram_api():
    """Instagram 연결 테스트 API"""
    try:
        instagram = get_instagram_service()
        result = await instagram.test_connection()
        return result
    except Exception as e:
        logger.error(f"Instagram 테스트 오류: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/analytics/performance")
async def get_performance_analytics():
    """성과 분석"""
    try:
        conn = sqlite3.connect("news_automation.db")
        cursor = conn.cursor()
        
        # 전체 통계
        cursor.execute("SELECT COUNT(*) FROM news_articles WHERE datetime(scraped_at) > datetime('now', '-7 days')")
        weekly_news = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM news_reels WHERE datetime(created_at) > datetime('now', '-7 days')")
        weekly_reels = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM news_posts WHERE status = 'posted' AND datetime(posted_at) > datetime('now', '-7 days')")
        weekly_posts = cursor.fetchone()[0]
        
        # 카테고리별 성과
        cursor.execute("""
            SELECT category, COUNT(*), AVG(viral_score)
            FROM news_articles 
            WHERE datetime(scraped_at) > datetime('now', '-7 days')
            GROUP BY category
            ORDER BY AVG(viral_score) DESC
        """)
        category_performance = cursor.fetchall()
        
        # 성공률 계산
        success_rate = (weekly_posts / max(weekly_reels, 1)) * 100
        
        conn.close()
        
        return {
            "success": True,
            "analytics": {
                "weekly_stats": {
                    "news_collected": weekly_news,
                    "reels_created": weekly_reels,
                    "posts_published": weekly_posts,
                    "success_rate": round(success_rate, 1)
                },
                "category_performance": [
                    {
                        "category": row[0],
                        "news_count": row[1],
                        "avg_viral_score": round(row[2], 2) if row[2] else 0
                    } for row in category_performance
                ],
                "top_categories": [row[0] for row in category_performance[:3]]
            }
        }
        
    except Exception as e:
        logger.error(f"성과 분석 오류: {e}")
        return {"success": False, "error": str(e)}

@app.delete("/api/cleanup/old-files")
async def cleanup_old_files():
    """오래된 파일 정리"""
    try:
        cleanup_count = 0
        
        # 7일 이상 된 비디오 파일 삭제
        if os.path.exists(VIDEO_OUTPUT_DIR):
            for filename in os.listdir(VIDEO_OUTPUT_DIR):
                file_path = os.path.join(VIDEO_OUTPUT_DIR, filename)
                if os.path.isfile(file_path):
                    file_age = time.time() - os.path.getctime(file_path)
                    if file_age > 7 * 24 * 3600:  # 7일
                        os.remove(file_path)
                        cleanup_count += 1
        
        # 7일 이상 된 오디오 파일 삭제
        if os.path.exists(AUDIO_OUTPUT_DIR):
            for filename in os.listdir(AUDIO_OUTPUT_DIR):
                file_path = os.path.join(AUDIO_OUTPUT_DIR, filename)
                if os.path.isfile(file_path):
                    file_age = time.time() - os.path.getctime(file_path)
                    if file_age > 7 * 24 * 3600:  # 7일
                        os.remove(file_path)
                        cleanup_count += 1
        
        # 임시 파일 정리
        if os.path.exists(TEMP_DIR):
            for filename in os.listdir(TEMP_DIR):
                file_path = os.path.join(TEMP_DIR, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    cleanup_count += 1
        
        return {
            "success": True,
            "message": f"{cleanup_count}개의 파일이 정리되었습니다",
            "cleaned_files": cleanup_count
        }
        
    except Exception as e:
        logger.error(f"파일 정리 오류: {e}")
        return {"success": False, "error": str(e)}

@app.delete("/api/clear-data")
async def clear_data():
    """데이터 초기화"""
    try:
        conn = sqlite3.connect("news_automation.db")
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM news_posts")
        cursor.execute("DELETE FROM generated_news_content")
        cursor.execute("DELETE FROM news_reels")
        cursor.execute("DELETE FROM news_articles")
        
        conn.commit()
        conn.close()
        
        return {"success": True, "message": "모든 데이터가 삭제되었습니다"}
        
    except Exception as e:
        logger.error(f"데이터 초기화 오류: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    print("🚀 ADVANCED NEWS AUTOMATION - AI 뉴스 & 릴스 자동화 플랫폼")
    print(f"📱 API 서버: http://{HOST}:{PORT}")
    print(f"📊 대시보드: http://{HOST}:{PORT}/dashboard")
    print(f"📚 API 문서: http://{HOST}:{PORT}/docs")
    print("=" * 80)
    
    if IS_RENDER:
        print("🌐 Render 환경에서 실행")
    else:
        print("💻 로컬 환경에서 실행")
    
    print("🎯 주요 기능:")
    print("  • ✅ 다중 소스 뉴스 크롤링")
    print("  • ✅ AI 바이럴 캡션 생성")
    print("  • ✅ 자동 릴스 제작")
    print("  • ✅ Instagram 릴스 자동 업로드")
    print("=" * 80)
    
    # 포트 설정 - Render 환경 고려
    port = int(os.environ.get("PORT", PORT))
    
    uvicorn.run(
        app,  # 문자열이 아닌 app 객체 직접 전달
        host="0.0.0.0",  # Render에서는 0.0.0.0 필수
        port=port, 
        reload=False  # 프로덕션에서는 reload 비활성화
    )