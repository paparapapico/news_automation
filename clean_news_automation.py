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
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
import gtts
from io import BytesIO
import base64
import shutil



# OpenAI 가져오기
try:
    import openai
    openai_version = openai.__version__
    print(f"📦 OpenAI 버전: {openai_version}")
    
    if openai_version.startswith('1.'):
        OPENAI_V1 = True
    else:
        OPENAI_V1 = False
        
except ImportError:
    print("❌ OpenAI 라이브러리가 설치되지 않았습니다.")
    OPENAI_V1 = False

logger = logging.getLogger(__name__)

# 환경변수 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ 환경변수 로드 완료")
except:
    print("⚠️ dotenv 없음 - 환경변수를 직접 설정하세요")

# 설정
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
HOST = os.getenv('HOST', '127.0.0.1')
PORT = int(os.getenv('PORT', 8000))

# 파일 경로 설정
UPLOAD_DIR = "uploads"
VIDEO_OUTPUT_DIR = "generated_videos"
AUDIO_OUTPUT_DIR = "generated_audio"
TEMP_DIR = "temp"

# 디렉토리 생성
for directory in [UPLOAD_DIR, VIDEO_OUTPUT_DIR, AUDIO_OUTPUT_DIR, TEMP_DIR]:
    os.makedirs(directory, exist_ok=True)

# JWT 설정
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-this-in-production')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# 보안 설정
security = HTTPBearer(auto_error=False)

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 뉴스 카테고리 설정 (확장됨)
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
    video_style: str = "trending"  # trending, news, minimal
    duration: int = 15  # 15초 (인스타그램 알고리즘 최적화)
    voice_speed: float = 1.2
    include_captions: bool = True
    background_music: bool = True

class NewsPostRequest(BaseModel):
    news_id: int
    caption_style: str = "viral"  # viral, engaging, informative
    include_hashtags: bool = True
    scheduled_time: Optional[str] = None

class MultiImagePostRequest(BaseModel):
    caption: str
    selected_images: List[str]
    hashtags: List[str]

# 향상된 뉴스 크롤링 시스템
class AdvancedNewsScrapingSystem:
    def __init__(self):
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 다양한 뉴스 소스 추가
        self.news_sources = {
            "google_news": {
                "url": "https://news.google.com/rss",
                "search_url": "https://news.google.com/search"
            },
            "naver_news": {
                "url": "https://news.naver.com/main/rss/read.nhn",
                "search_url": "https://search.naver.com/search.naver"
            },
            "daum_news": {
                "url": "https://media.daum.net/rss/",
                "search_url": "https://search.daum.net/search"
            }
        }
    
    async def _get_session(self):
        """aiohttp 세션 lazy 초기화"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    def _generate_title_hash(self, title: str) -> str:
        """제목 해시 생성 (중복 검사용)"""
        # 특수문자 제거하고 소문자로 변환
        cleaned_title = re.sub(r'[^\w\s]', '', title.lower())
        # 공백 정규화
        cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
        # 해시 생성
        return hashlib.md5(cleaned_title.encode('utf-8')).hexdigest()
    
    def _is_duplicate_news(self, title: str, category: str) -> bool:
        """중복 뉴스 검사 (최근 24시간)"""
        try:
            title_hash = self._generate_title_hash(title)
            
            conn = sqlite3.connect("news_automation.db")
            cursor = conn.cursor()
            
            # 같은 카테고리에서 같은 해시가 있는지 확인 (최근 24시간)
            cursor.execute("""
                SELECT COUNT(*) FROM news_articles 
                WHERE title_hash = ? AND category = ? 
                AND datetime(scraped_at) > datetime('now', '-1 days')
            """, (title_hash, category))
            
            count = cursor.fetchone()[0]
            conn.close()
            
            return count > 0
            
        except Exception as e:
            logger.error(f"중복 검사 오류: {e}")
            return False
    
    async def scrape_latest_news(self, category: str, max_articles: int = 10) -> List[Dict]:
        """최신 뉴스 크롤링 (다중 소스)"""
        try:
            all_news = []
            
            # Google News 크롤링
            google_news = await self._scrape_google_news(category, max_articles)
            all_news.extend(google_news)
            
            # 중복 제거
            unique_news = self._filter_duplicate_news(all_news)
            
            # 바이럴 점수 기반 정렬
            sorted_news = sorted(unique_news, key=lambda x: x['viral_score'], reverse=True)
            
            return sorted_news[:max_articles]
            
        except Exception as e:
            logger.error(f"뉴스 크롤링 오류: {e}")
            return []
    
    async def _scrape_google_news(self, category: str, max_articles: int) -> List[Dict]:
        """Google News RSS 크롤링 (개선)"""
        try:
            category_info = NEWS_CATEGORIES.get(category, NEWS_CATEGORIES["domestic"])
            news_list = []
            
            session = await self._get_session()
            
            # 트렌딩 키워드와 일반 키워드 결합
            all_terms = category_info["search_terms"] + category_info.get("trending_terms", [])
            
            for search_term in all_terms[:3]:
                try:
                    # URL 인코딩
                    encoded_term = urllib.parse.quote(search_term)
                    rss_url = f"https://news.google.com/rss/search?q={encoded_term}&hl=ko&gl=KR&ceid=KR:ko"
                    
                    async with session.get(rss_url, headers=self.headers, timeout=15) as response:
                        if response.status == 200:
                            content = await response.text()
                            feed = feedparser.parse(content)
                            
                            for entry in feed.entries[:max_articles//3]:
                                # 제목 정리
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
                                
                except Exception as e:
                    logger.warning(f"Google News 검색어 '{search_term}' 오류: {e}")
                    continue
            
            return news_list
            
        except Exception as e:
            logger.error(f"Google News 크롤링 오류: {e}")
            return []
    
    def _filter_duplicate_news(self, news_list: List[Dict]) -> List[Dict]:
        """중복 뉴스 필터링"""
        unique_news = []
        seen_hashes = set()
        
        for news in news_list:
            title_hash = self._generate_title_hash(news['title'])
            
            # 현재 세션에서 중복 확인
            if title_hash in seen_hashes:
                continue
            
            # DB에서 중복 확인
            if self._is_duplicate_news(news['title'], news['category']):
                logger.info(f"중복 뉴스 제외: {news['title'][:50]}...")
                continue
            
            seen_hashes.add(title_hash)
            news['title_hash'] = title_hash
            unique_news.append(news)
        
        logger.info(f"중복 제거 결과: {len(news_list)} → {len(unique_news)}")
        return unique_news
    
    def _calculate_viral_score(self, title: str) -> float:
        """바이럴 점수 계산 (인스타그램 알고리즘 최적화)"""
        score = 1.0
        title_lower = title.lower()
        
        # 자극적인 키워드 (높은 점수)
        viral_keywords = [
            "긴급", "속보", "충격", "논란", "폭등", "폭락", "급등", "급락", 
            "사상최고", "사상최저", "역대최대", "파격", "깜짝", "반전",
            "breaking", "urgent", "shock", "surge", "plunge", "exclusive",
            "처음", "최초", "드디어", "결국", "마침내", "놀라운"
        ]
        for keyword in viral_keywords:
            if keyword in title_lower:
                score += 3.0
        
        # 감정을 자극하는 키워드
        emotion_keywords = [
            "분노", "눈물", "감동", "화제", "대박", "실화", "믿을수없는",
            "amazing", "incredible", "unbelievable", "shocking"
        ]
        for keyword in emotion_keywords:
            if keyword in title_lower:
                score += 2.5
        
        # 숫자/퍼센트 포함 시 점수
        if re.search(r'\d+%|\d+억|\d+만|\d+\$|\d+배|\d+년만에', title):
            score += 2.0
        
        # 유명 인물/브랜드
        famous_entities = [
            "삼성", "애플", "테슬라", "비트코인", "대통령", "trump", "biden",
            "bts", "블랙핑크", "아이유", "손흥민", "이재용"
        ]
        for entity in famous_entities:
            if entity in title_lower:
                score += 1.5
        
        # 의문문/느낌표
        if '?' in title or '!' in title:
            score += 1.0
        
        # 제목 길이 적절성 (인스타그램 최적화)
        if 15 <= len(title) <= 60:
            score += 1.5
        elif len(title) > 80:
            score -= 1.0
        
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
        
        # 폰트 설정 (Windows 경로 추가)
        self.font_paths = {
            "bold": self._find_font(["NanumGothicBold.ttf", "malgun.ttf", "arial-bold.ttf", "DejaVuSans-Bold.ttf"]),
            "regular": self._find_font(["NanumGothic.ttf", "malgun.ttf", "arial.ttf", "DejaVuSans.ttf"])
        }
    
    def _find_font(self, font_names: List[str]) -> str:
        """시스템에서 폰트 찾기"""
        font_paths = [
            "C:/Windows/Fonts/",  # Windows
            "/System/Library/Fonts/",  # macOS
            "/usr/share/fonts/",  # Linux
            "./fonts/",
            ""
        ]
        
        for font_name in font_names:
            for font_path in font_paths:
                full_path = os.path.join(font_path, font_name)
                if os.path.exists(full_path):
                    return full_path
        
        return None  # 기본 폰트 사용
    
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
            
            # 3단계: 자막 생성
            caption_result = await self._generate_captions(news_data)
            if not caption_result["success"]:
                return caption_result
            
            # 4단계: 최종 비디오 합성
            final_result = await self._compose_final_video(
                audio_result["audio_path"],
                visual_result["visual_path"],
                caption_result["captions"],
                news_data,
                style,
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
            # 뉴스 스크립트 생성 (duration에 맞게 조정)
            script = self._create_news_script(news_data, duration)
            
            # gTTS로 음성 생성
            tts = gtts.gTTS(text=script, lang='ko', slow=False)
            
            # 임시 파일에 저장
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
        """뉴스 스크립트 생성 (duration 최적화)"""
        title = news_data['title']
        category = NEWS_CATEGORIES.get(news_data['category'], {}).get('name', '뉴스')
        
        # duration에 따른 스크립트 길이 조정 (대략 150자/분)
        target_chars = int(duration * 2.5)  # 15초 = 약 37자
        
        if duration <= 15:
            # 짧은 버전 (15초)
            script = f"{category} 속보입니다. {title}. 이 소식에 대한 여러분의 생각은 어떠신가요?"
        elif duration <= 30:
            # 중간 버전 (30초)
            summary = news_data.get('summary', title)[:100]
            script = f"{category} 긴급 뉴스를 전해드립니다. {title}. {summary}. 계속해서 관련 소식을 전해드리겠습니다."
        else:
            # 긴 버전 (60초)
            summary = news_data.get('summary', title)
            script = f"안녕하세요. {category} 속보를 전해드립니다. {title}. {summary}. 이 사건의 자세한 내용과 앞으로의 전망에 대해 계속 주목해 주시기 바랍니다."
        
        # 목표 길이에 맞게 조정
        if len(script) > target_chars:
            script = script[:target_chars-3] + "..."
        
        return script
    
    async def _create_visual_content(self, news_data: Dict, style: str, duration: int) -> Dict:
        """비주얼 콘텐츠 생성"""
        try:
            # 스타일별 비주얼 생성
            if style == "trending":
                visual_path = await self._create_trending_visual(news_data, duration)
            elif style == "news":
                visual_path = await self._create_news_visual(news_data, duration)
            else:  # minimal
                visual_path = await self._create_minimal_visual(news_data, duration)
            
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
    
    async def _create_trending_visual(self, news_data: Dict, duration: int) -> str:
        """트렌딩 스타일 비주얼 생성 (인스타그램 알고리즘 최적화)"""
        try:
            # 9:16 비율 (1080x1920)
            width, height = 1080, 1920
            fps = 30
            
            # 배경 그라데이션 생성
            background_frames = []
            for frame_num in range(int(duration * fps)):
                # 동적 그라데이션 배경
                img = Image.new('RGB', (width, height))
                draw = ImageDraw.Draw(img)
                
                # 시간에 따른 색상 변화
                hue = (frame_num * 2) % 360
                color1 = self._hsv_to_rgb(hue, 0.8, 0.9)
                color2 = self._hsv_to_rgb((hue + 60) % 360, 0.6, 0.7)
                
                # 그라데이션 그리기
                for y in range(height):
                    ratio = y / height
                    r = int(color1[0] * (1-ratio) + color2[0] * ratio)
                    g = int(color1[1] * (1-ratio) + color2[1] * ratio)
                    b = int(color1[2] * (1-ratio) + color2[2] * ratio)
                    draw.line([(0, y), (width, y)], fill=(r, g, b))
                
                # 제목 텍스트 추가 (기본 폰트 사용)
                # 제목을 여러 줄로 분할
                title_lines = self._wrap_text(news_data['title'], 12)
                
                # 텍스트 그림자 효과
                shadow_offset = 5
                for i, line in enumerate(title_lines[:3]):  # 최대 3줄
                    y_pos = height//2 - 100 + i * 100
                    
                    # 그림자
                    draw.text((width//2 - len(line)*20 + shadow_offset, y_pos + shadow_offset), 
                             line, fill=(0, 0, 0), anchor="mm")
                    
                    # 메인 텍스트
                    draw.text((width//2, y_pos), line, fill=(255, 255, 255), anchor="mm")
                
                # numpy 배열로 변환
                frame_array = np.array(img)
                background_frames.append(frame_array)
            
            # 비디오 파일로 저장
            visual_filename = f"visual_trending_{news_data['id']}_{int(time.time())}.mp4"
            visual_path = os.path.join(self.temp_dir, visual_filename)
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(visual_path, fourcc, fps, (width, height))
            
            for frame in background_frames:
                # BGR로 변환 (OpenCV 요구사항)
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                out.write(frame_bgr)
            
            out.release()
            
            logger.info(f"✅ 트렌딩 비주얼 생성 완료: {visual_path}")
            return visual_path
            
        except Exception as e:
            logger.error(f"트렌딩 비주얼 생성 오류: {e}")
            raise
    
    async def _create_news_visual(self, news_data: Dict, duration: int) -> str:
        """뉴스 스타일 비주얼 생성"""
        # 간단한 뉴스 스타일 구현
        return await self._create_trending_visual(news_data, duration)
    
    async def _create_minimal_visual(self, news_data: Dict, duration: int) -> str:
        """미니멀 스타일 비주얼 생성"""
        # 간단한 미니멀 스타일 구현
        return await self._create_trending_visual(news_data, duration)
    
    def _hsv_to_rgb(self, h: float, s: float, v: float) -> tuple:
        """HSV to RGB 변환"""
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(h/360, s, v)
        return (int(r*255), int(g*255), int(b*255))
    
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
    
    async def _generate_captions(self, news_data: Dict) -> Dict:
        """자막 생성"""
        try:
            # 간단한 자막 데이터 생성
            captions = [
                {"start": 0, "end": 3, "text": "속보"},
                {"start": 3, "end": 10, "text": news_data['title'][:30]},
                {"start": 10, "end": 15, "text": "더 많은 뉴스는 팔로우!"}
            ]
            
            return {
                "success": True,
                "captions": captions
            }
            
        except Exception as e:
            logger.error(f"자막 생성 오류: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _compose_final_video(self, audio_path: str, visual_path: str, captions: List[Dict], 
                                 news_data: Dict, style: str, duration: int) -> Dict:
        """최종 비디오 합성 (moviepy 설치 체크)"""
        try:
            # MoviePy가 설치되어 있지 않으면 기본 비디오만 반환
            try:
                from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
            except ImportError:
                logger.warning("MoviePy가 설치되지 않음. 기본 비디오만 반환합니다.")
                
                # 파일 크기 확인
                file_size = os.path.getsize(visual_path) / (1024 * 1024)  # MB
                
                return {
                    "success": True,
                    "video_path": visual_path,
                    "file_size_mb": round(file_size, 1),
                    "duration": duration,
                    "message": f"기본 비디오가 생성되었습니다! ({file_size:.1f}MB)"
                }
            
            # MoviePy를 사용한 비디오 합성
            video_clip = VideoFileClip(visual_path)
            audio_clip = AudioFileClip(audio_path)
            
            # 오디오 길이에 맞게 비디오 조정
            if video_clip.duration > audio_clip.duration:
                video_clip = video_clip.subclip(0, audio_clip.duration)
            elif video_clip.duration < audio_clip.duration:
                audio_clip = audio_clip.subclip(0, video_clip.duration)
            
            # 오디오 추가
            final_video = video_clip.set_audio(audio_clip)
            
            # 최종 비디오 저장
            output_filename = f"reel_{news_data['id']}_{int(time.time())}.mp4"
            output_path = os.path.join(self.output_dir, output_filename)
            
            final_video.write_videofile(
                output_path,
                fps=30,
                audio_codec='aac',
                codec='libx264',
                verbose=False,
                logger=None
            )
            
            # 클립 메모리 해제
            video_clip.close()
            audio_clip.close()
            final_video.close()
            
            # 파일 크기 확인
            file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
            
            logger.info(f"🎬 릴스 제작 완료: {output_path} ({file_size:.1f}MB)")
            
            return {
                "success": True,
                "video_path": output_path,
                "file_size_mb": round(file_size, 1),
                "duration": duration,
                "message": f"릴스가 성공적으로 제작되었습니다! ({file_size:.1f}MB)"
            }
            
        except Exception as e:
            logger.error(f"최종 비디오 합성 오류: {e}")
            
            # 오류 발생 시 기본 비디오 반환
            if os.path.exists(visual_path):
                file_size = os.path.getsize(visual_path) / (1024 * 1024)
                return {
                    "success": True,
                    "video_path": visual_path,
                    "file_size_mb": round(file_size, 1),
                    "duration": duration,
                    "message": f"기본 비디오가 생성되었습니다! ({file_size:.1f}MB)"
                }
            else:
                return {
                    "success": False,
                    "error": str(e),
                    "message": "비디오 합성 중 오류가 발생했습니다."
                }

# AI 콘텐츠 생성 시스템 (향상됨)
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
            
            print(f"✅ OpenAI 클라이언트 초기화 완료 (v{openai.__version__})")
            
        except Exception as e:
            logger.error(f"OpenAI 클라이언트 초기화 오류: {e}")
            self.openai_client = None
    
    async def generate_viral_caption(self, news_data: Dict, style: str = "viral") -> Dict:
        """바이럴 캡션 생성 (인스타그램 알고리즘 최적화)"""
        
        if not self.openai_client:
            return self._generate_fallback_caption(news_data)
        
        style_prompts = {
            "viral": "바이럴되기 쉬운 자극적이고 호기심을 자극하는 스타일로",
            "engaging": "참여를 유도하는 매력적인 스타일로", 
            "informative": "정보 전달에 중점을 둔 전문적인 스타일로",
            "trendy": "트렌드를 반영한 MZ세대 친화적인 스타일로"
        }
        
        prompt = f"""
다음 뉴스를 바탕으로 인스타그램 릴스/포스트용 캡션을 {style_prompts.get(style, '자연스러운 스타일로')} 작성해주세요.

뉴스 제목: {news_data['title']}
뉴스 요약: {news_data['summary']}
카테고리: {news_data['category']}

인스타그램 알고리즘 최적화 요구사항:
1. 첫 3초 안에 시선을 사로잡는 훅 문장
2. 호기심을 자극하는 질문 포함
3. 이모지 3-5개 전략적 사용
4. 댓글을 유도하는 CTA(Call to Action)
5. 2-4줄의 간결한 구성
6. 트렌딩 용어 활용

예시 구조:
🚨 [충격적인 훅] 
[핵심 정보 + 감정 자극]
[질문으로 참여 유도]
[CTA + 이모지]

캡션만 답변하세요:
"""
        
        try:
            if OPENAI_V1:
                response = self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": "당신은 인스타그램 알고리즘을 잘 이해하는 전문 SNS 마케터입니다. 바이럴 콘텐츠 제작의 전문가입니다."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=400,
                    temperature=0.9
                )
                caption = response.choices[0].message.content.strip()
            else:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": "당신은 인스타그램 알고리즘을 잘 이해하는 전문 SNS 마케터입니다. 바이럴 콘텐츠 제작의 전문가입니다."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=400,
                    temperature=0.9
                )
                caption = response.choices[0].message.content.strip()
            
            return {
                'caption': caption,
                'keypoint': '바이럴 뉴스',
                'target_emotion': '호기심/충격',
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
        
        prompt = f"""
다음 뉴스에 적합한 인스타그램 해시태그를 생성해주세요.

뉴스 제목: {news_data['title']}
카테고리: {news_data['category']}

해시태그 요구사항:
1. 총 15-20개 (최적 노출을 위한 개수)
2. 인기/트렌딩 해시태그 포함
3. 니치 해시태그와 브로드 해시태그 균형
4. 카테고리별 특화 해시태그
5. 한국어/영어 혼합

해시태그만 나열해서 답변 (# 포함, 공백으로 구분):
"""
        
        try:
            if OPENAI_V1:
                response = self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=300,
                    temperature=0.8
                )
                hashtags_text = response.choices[0].message.content.strip()
            else:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=300,
                    temperature=0.8
                )
                hashtags_text = response.choices[0].message.content.strip()
            
            hashtags = [tag.strip() for tag in hashtags_text.split() if tag.startswith('#')]
            
            # 카테고리별 필수 해시태그 추가
            base_hashtags = self._get_trending_hashtags(news_data['category'])
            hashtags.extend(base_hashtags)
            
            # 중복 제거 및 최적화
            unique_hashtags = list(dict.fromkeys(hashtags))
            return unique_hashtags[:20]
            
        except Exception as e:
            logger.error(f"해시태그 생성 오류: {e}")
            return self._get_category_hashtags(news_data['category'])
    
    def _get_trending_hashtags(self, category: str) -> List[str]:
        """카테고리별 트렌딩 해시태그"""
        trending_hashtags = {
            "stock": [
                "#주식", "#투자", "#재테크", "#경제", "#코스피", "#증시", 
                "#stockmarket", "#investment", "#money", "#finance",
                "#부자되기", "#주린이", "#경제뉴스", "#급등", "#급락"
            ],
            "politics": [
                "#정치", "#뉴스", "#대통령", "#국회", "#정부", "#시사",
                "#politics", "#news", "#breaking", "#korea",
                "#정치뉴스", "#속보", "#긴급", "#논란", "#발언"
            ],
            "international": [
                "#해외뉴스", "#국제뉴스", "#세계뉴스", "#글로벌", "#외신",
                "#worldnews", "#international", "#global", "#breaking",
                "#미국", "#중국", "#일본", "#유럽", "#전쟁"
            ],
            "domestic": [
                "#국내뉴스", "#사회이슈", "#시사", "#한국뉴스", "#속보",
                "#koreanews", "#society", "#issue", "#breaking",
                "#사건", "#사고", "#논란", "#이슈", "#화제"
            ],
            "technology": [
                "#기술뉴스", "#IT뉴스", "#인공지능", "#테크", "#혁신", "#AI",
                "#technology", "#tech", "#innovation", "#startup",
                "#삼성", "#애플", "#구글", "#신제품", "#출시"
            ],
            "entertainment": [
                "#연예뉴스", "#연예인", "#아이돌", "#케이팝", "#드라마",
                "#entertainment", "#kpop", "#celebrity", "#drama",
                "#BTS", "#블랙핑크", "#아이유", "#데뷔", "#컴백"
            ]
        }
        
        # 공통 트렌딩 해시태그 추가
        common_trending = [
            "#트렌드", "#화제", "#이슈", "#팔로우", "#좋아요",
            "#trending", "#viral", "#fyp", "#reels", "#instagood"
        ]
        
        category_tags = trending_hashtags.get(category, ["#뉴스", "#이슈"])
        return category_tags + common_trending
    
    def _get_category_hashtags(self, category: str) -> List[str]:
        """기본 카테고리별 해시태그"""
        return self._get_trending_hashtags(category)[:15]
    
    def _generate_fallback_caption(self, news_data: Dict) -> Dict:
        """폴백 캡션 생성 (AI 없이)"""
        title = news_data['title']
        category_name = NEWS_CATEGORIES.get(news_data['category'], {}).get('name', '뉴스')
        
        viral_hooks = [
            "🚨 이거 진짜야?",
            "😱 충격적인 소식!",
            "🔥 지금 화제!",
            "⚡ 속보 터졌다!",
            "💥 대박 사건!"
        ]
        
        hook = random.choice(viral_hooks)
        
        return {
            'caption': f"{hook}\n\n{title}\n\n여러분 생각은? 댓글로 알려주세요! 👇\n\n#속보 #뉴스 #이슈",
            'keypoint': '뉴스 속보',
            'target_emotion': '호기심',
            'style': 'viral'
        }

# Instagram 서비스 클래스 확장 (릴스 지원)
class AdvancedInstagramService:
    def __init__(self):
        self.access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN')
        self.business_account_id = os.getenv('INSTAGRAM_BUSINESS_ACCOUNT_ID')
        self.base_url = "https://graph.facebook.com"
        self.api_version = "v18.0"
        
    def validate_credentials(self) -> bool:
        """인증 정보 유효성 검사"""
        if not self.access_token or not self.business_account_id:
            logger.error("Instagram 인증 정보가 설정되지 않았습니다.")
            return False
        return True
    
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
            
            logger.info(f"Instagram API 테스트 - 상태코드: {response.status_code}")
            logger.info(f"Instagram API 응답: {response.text[:200]}...")
            
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
        """릴스 업로드 (비디오 파일)"""
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

# 데이터베이스 초기화 (릴스 테이블 추가)
def init_enhanced_db():
    """향상된 데이터베이스 초기화"""
    try:
        conn = sqlite3.connect("news_automation.db")
        cursor = conn.cursor()
        
        # 기존 뉴스 테이블 (title_hash 컬럼 추가)
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
        
        # title_hash 컬럼이 없으면 추가
        try:
            cursor.execute("ALTER TABLE news_articles ADD COLUMN title_hash TEXT")
        except sqlite3.OperationalError:
            pass
        
        try:
            cursor.execute("ALTER TABLE news_articles ADD COLUMN viral_score REAL")
        except sqlite3.OperationalError:
            pass
        
        # 릴스 제작 테이블 (새로 추가)
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
        
        # 생성된 콘텐츠 테이블 (확장)
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
        
        # 포스팅 기록 테이블 (릴스 지원 추가)
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
        
        # 인덱스 생성
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_title_hash ON news_articles(title_hash)",
            "CREATE INDEX IF NOT EXISTS idx_category_scraped ON news_articles(category, scraped_at)",
            "CREATE INDEX IF NOT EXISTS idx_viral_score ON news_articles(viral_score DESC)",
            "CREATE INDEX IF NOT EXISTS idx_posts_status ON news_posts(status, posted_at)",
            "CREATE INDEX IF NOT EXISTS idx_reels_status ON news_reels(status, created_at)"
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)
        
        conn.commit()
        conn.close()
        logger.info("✅ 향상된 데이터베이스 초기화 완료")
        return True
    except Exception as e:
        logger.error(f"❌ DB 초기화 오류: {e}")
        return False

# FastAPI 앱 초기화
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ADVANCED NEWS AUTOMATION - AI 뉴스 & 릴스 자동화 플랫폼 시작")
    init_enhanced_db()
    yield
    # 앱 종료 시 세션 정리
    if hasattr(app.state, 'news_scraper'):
        await app.state.news_scraper.close()

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

app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # 기본 빈 응답 또는 실제 favicon 파일 반환
    return Response(status_code=204)

# 정적 파일 서빙
try:
    app.mount("/generated_videos", StaticFiles(directory=VIDEO_OUTPUT_DIR), name="videos")
    app.mount("/generated_audio", StaticFiles(directory=AUDIO_OUTPUT_DIR), name="audio")
except Exception as e:
    logger.warning(f"정적 파일 마운트 실패: {e}")

# 서비스 인스턴스
news_scraper = None
content_generator = None
instagram_service = None
reels_producer = None

def get_news_scraper():
    global news_scraper
    if news_scraper is None:
        news_scraper = AdvancedNewsScrapingSystem()
    return news_scraper

def get_content_generator():
    global content_generator
    if content_generator is None:
        content_generator = AdvancedContentGenerator()
    return content_generator

def get_instagram_service():
    global instagram_service
    if instagram_service is None:
        instagram_service = AdvancedInstagramService()
    return instagram_service

def get_reels_producer():
    global reels_producer
    if reels_producer is None:
        reels_producer = ReelsProductionSystem()
    return reels_producer

# API 라우트들

@app.get("/")
async def home():
    """향상된 홈페이지"""
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
    try:
        possible_paths = ["dashboard.html", "./dashboard.html", "/app/dashboard.html"]
        
        for path in possible_paths:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
        # 파일을 찾을 수 없으면 기본 대시보드 반환
        return get_default_dashboard_html()
    
    except Exception as e:
        logger.error(f"대시보드 로드 오류: {e}")
        return get_default_dashboard_html()

def get_default_dashboard_html():
    """기본 대시보드 HTML"""
    return """
    <!DOCTYPE html>
    <html><head><title>News Automation Dashboard</title></head>
    <body>
    <h1>NEWS AUTOMATION - Render 배포 성공!</h1>
    <p>API 서버가 정상 작동 중입니다.</p>
    <p><a href="/docs">API 문서 보기</a></p>
    <p><a href="/health">시스템 상태 확인</a></p>
    </body></html>
    """


@app.post("/api/scrape-news")
async def scrape_news_api(request: NewsRequest):
    """향상된 뉴스 수집 API"""
    try:
        scraper = get_news_scraper()
        news_list = await scraper.scrape_latest_news(request.category, request.max_articles)
        
        if not news_list:
            return {"success": False, "message": "수집된 새로운 뉴스가 없습니다"}
        
        # DB에 저장
        saved_news = []
        conn = sqlite3.connect("news_automation.db")
        cursor = conn.cursor()
        
        for news in news_list:
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
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": f"{len(saved_news)}개의 새로운 뉴스를 수집했습니다",
            "news": saved_news,
            "highest_viral_score": max([n['viral_score'] for n in saved_news]) if saved_news else 0
        }
        
    except Exception as e:
        logger.error(f"뉴스 수집 API 오류: {e}")
        return {"success": False, "error": str(e)}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "news_automation"}

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

@app.post("/api/post-reel-to-instagram/{reel_id}")
async def post_reel_to_instagram_api(reel_id: int):
    """릴스 Instagram 업로드 API"""
    try:
        # 릴스 데이터 조회
        conn = sqlite3.connect("news_automation.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nr.*, na.title, na.category 
            FROM news_reels nr
            JOIN news_articles na ON nr.news_id = na.id
            WHERE nr.id = ?
        """, (reel_id,))
        
        row = cursor.fetchone()
        if not row:
            return {"success": False, "message": "릴스를 찾을 수 없습니다"}
        
        # 릴스 데이터 구성
        video_path = row[2]
        news_title = row[9]
        category = row[10]
        
        # 바이럴 캡션 생성
        generator = get_content_generator()
        news_data = {
            'id': row[1],
            'title': news_title,
            'category': category,
            'summary': news_title  # 간단한 경우
        }
        
        caption_data = await generator.generate_viral_caption(news_data, "viral")
        hashtags = await generator.generate_trending_hashtags(news_data)
        
        # 전체 캡션 생성
        full_caption = f"{caption_data['caption']}\n\n{' '.join(hashtags[:25])}"
        
        # Instagram 릴스 업로드 (비디오 파일)
        instagram = get_instagram_service()
        
        # 비디오 파일을 public URL로 변환 (실제 구현에서는 CDN 등 사용)
        video_url = f"http://{HOST}:{PORT}/generated_videos/{os.path.basename(video_path)}"
        
        result = await instagram.post_reel_with_video(full_caption, video_url)
        
        # 포스팅 기록 저장
        status = 'posted' if result.get('success') else 'failed'
        error_message = None if result.get('success') else str(result.get('error', ''))
        
        cursor.execute("""
            INSERT INTO news_posts 
            (news_id, reel_id, platform, post_type, post_id, caption, hashtags, media_urls, 
             posted_at, status, error_message, instagram_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row[1],  # news_id
            reel_id,
            'instagram',
            'reel',
            result.get('post_id', ''),
            caption_data['caption'],
            json.dumps(hashtags),
            video_url,
            datetime.now().isoformat(),
            status,
            error_message,
            result.get('instagram_url', '')
        ))
        
        conn.commit()
        conn.close()
        
        return result
        
    except Exception as e:
        logger.error(f"릴스 Instagram 업로드 오류: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/automation/full-reel-process")
async def full_reel_automation():
    """전체 릴스 자동화 프로세스"""
    try:
        results = {
            "scraped_news": 0,
            "created_reels": 0,
            "posted_reels": 0,
            "errors": []
        }
        
        # 1단계: 고 바이럴 점수 뉴스 수집
        categories = list(NEWS_CATEGORIES.keys())
        scraper = get_news_scraper()
        producer = get_reels_producer()
        generator = get_content_generator()
        instagram = get_instagram_service()
        
        all_news = []
        
        for category in categories:
            try:
                logger.info(f"📰 {category} 카테고리 뉴스 수집 중...")
                news_list = await scraper.scrape_latest_news(category, 3)
                
                if news_list:
                    # DB에 저장
                    conn = sqlite3.connect("news_automation.db")
                    cursor = conn.cursor()
                    
                    for news in news_list:
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
                        news['id'] = cursor.lastrowid
                        all_news.append(news)
                    
                    conn.commit()
                    conn.close()
                    
                    results["scraped_news"] += len(news_list)
                
            except Exception as e:
                results["errors"].append(f"{category} 수집 오류: {str(e)}")
                continue
        
        # 2단계: 바이럴 점수 기준 상위 뉴스 선별 (최대 3개)
        top_viral_news = sorted(all_news, key=lambda x: x['viral_score'], reverse=True)[:3]
        
        for news in top_viral_news:
            try:
                logger.info(f"🎬 뉴스 ID {news['id']} 릴스 제작 중...")
                
                # 릴스 제작
                reel_result = await producer.create_news_reel(news, "trending", 15)
                
                if reel_result["success"]:
                    # DB에 릴스 저장
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
                        reel_result["file_size_mb"],
                        datetime.now().isoformat(),
                        'created'
                    ))
                    
                    reel_id = cursor.lastrowid
                    conn.commit()
                    conn.close()
                    
                    results["created_reels"] += 1
                    
                    # 3단계: Instagram 업로드
                    logger.info(f"📱 릴스 ID {reel_id} Instagram 업로드 중...")
                    
                    # 바이럴 캡션 생성
                    caption_data = await generator.generate_viral_caption(news, "viral")
                    hashtags = await generator.generate_trending_hashtags(news)
                    full_caption = f"{caption_data['caption']}\n\n{' '.join(hashtags[:25])}"
                    
                    # 비디오 URL 생성
                    video_url = f"http://{HOST}:{PORT}/generated_videos/{os.path.basename(reel_result['video_path'])}"
                    
                    # Instagram 업로드
                    upload_result = await instagram.post_reel_with_video(full_caption, video_url)
                    
                    # 결과 기록
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
                        logger.info(f"✅ 릴스 자동화 성공: {news['title'][:50]}...")
                    else:
                        results["errors"].append(f"릴스 업로드 실패: {upload_result.get('message', '알 수 없는 오류')}")
                    
                    # 업로드 간격 (Instagram API 제한)
                    await asyncio.sleep(15)
                
                else:
                    results["errors"].append(f"릴스 제작 실패: {reel_result.get('message', '알 수 없는 오류')}")
                
            except Exception as e:
                results["errors"].append(f"뉴스 ID {news['id']} 처리 오류: {str(e)}")
                continue
        
        # 결과 요약
        success_rate = (results["posted_reels"] / max(results["created_reels"], 1)) * 100
        
        return {
            "success": True,
            "message": f"릴스 자동화 완료 (성공률: {success_rate:.1f}%)",
            "results": results,
            "top_viral_scores": [n['viral_score'] for n in top_viral_news]
        }
        
    except Exception as e:
        logger.error(f"전체 릴스 자동화 오류: {e}")
        return {"success": False, "error": str(e)}

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
                        "avg_viral_score": round(row[2], 2)
                    } for row in category_performance
                ],
                "top_categories": [row[0] for row in category_performance[:3]]
            }
        }
        
    except Exception as e:
        logger.error(f"성과 분석 오류: {e}")
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

@app.delete("/api/cleanup/old-files")
async def cleanup_old_files():
    """오래된 파일 정리"""
    try:
        cleanup_count = 0
        
        # 7일 이상 된 비디오 파일 삭제
        for filename in os.listdir(VIDEO_OUTPUT_DIR):
            file_path = os.path.join(VIDEO_OUTPUT_DIR, filename)
            if os.path.isfile(file_path):
                file_age = time.time() - os.path.getctime(file_path)
                if file_age > 7 * 24 * 3600:  # 7일
                    os.remove(file_path)
                    cleanup_count += 1
        
        # 7일 이상 된 오디오 파일 삭제
        for filename in os.listdir(AUDIO_OUTPUT_DIR):
            file_path = os.path.join(AUDIO_OUTPUT_DIR, filename)
            if os.path.isfile(file_path):
                file_age = time.time() - os.path.getctime(file_path)
                if file_age > 7 * 24 * 3600:  # 7일
                    os.remove(file_path)
                    cleanup_count += 1
        
        # 임시 파일 정리
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

@app.get("/health")
async def enhanced_health_check():
    """향상된 시스템 상태 확인"""
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
        
        # 디스크 사용량 확인
        video_dir_size = 0
        try:
            video_dir_size = sum(os.path.getsize(os.path.join(VIDEO_OUTPUT_DIR, f)) 
                               for f in os.listdir(VIDEO_OUTPUT_DIR) if os.path.isfile(os.path.join(VIDEO_OUTPUT_DIR, f)))
        except:
            pass
        video_dir_size_mb = video_dir_size / (1024 * 1024)
        
        return {
            "status": "healthy",
            "database": "connected",
            "services": {
                "news_scraper": "active",
                "reels_producer": "active", 
                "content_generator": "active",
                "openai_available": generator.openai_client is not None
            },
            "statistics": {
                "total_news": total_news,
                "total_reels": total_reels,
                "posted_content": posted_content,
                "avg_viral_score": round(avg_viral_score, 2),
                "video_storage_mb": round(video_dir_size_mb, 1)
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    print("🚀 ADVANCED NEWS AUTOMATION - AI 뉴스 & 릴스 자동화 플랫폼")
    print(f"📱 API 서버: http://{HOST}:{PORT}")
    print(f"📊 대시보드: http://{HOST}:{PORT}/dashboard")
    print(f"📚 API 문서: http://{HOST}:{PORT}/docs")
    print("=" * 80)
    print("🎯 새로운 기능:")
    print("  • ✅ 다중 소스 뉴스 크롤링 (Google News)")
    print("  • ✅ AI 바이럴 캡션 생성")
    print("  • ✅ 자동 릴스 제작 (TTS + 비주얼)")
    print("  • ✅ Instagram 릴스 자동 업로드")
    print("  • ✅ 바이럴 점수 기반 우선순위")
    print("  • ✅ 성과 분석 및 모니터링")
    print("=" * 80)
    
    # 수정된 코드:
if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("clean_news_automation:app", host="0.0.0.0", port=port, reload=False)