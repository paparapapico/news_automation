#!/usr/bin/env python3
"""
Railway 배포를 위한 간단한 시작 스크립트
포트 문제를 근본적으로 해결합니다.
"""

import os
import sys
import subprocess

def main():
    # 포트 설정
    port = os.environ.get('PORT', '8000')
    
    # 포트가 정수인지 확인
    try:
        port_int = int(port)
        print(f"✅ 포트 설정: {port_int}")
    except ValueError:
        print(f"❌ 잘못된 포트 값: {port}, 기본값 8000 사용")
        port_int = 8000
    
    # Railway 환경 설정
    os.environ['RAILWAY'] = 'true'
    os.environ['ENVIRONMENT'] = 'production'
    
    print("🚀 Railway에서 News Automation 시작...")
    print(f"📍 포트: {port_int}")
    print(f"🌐 호스트: 0.0.0.0")
    
    # uvicorn 명령어 구성
    cmd = [
        'uvicorn',
        'clean_news_automation:app',
        '--host', '0.0.0.0',
        '--port', str(port_int),
        '--workers', '1'
    ]
    
    print(f"🔧 실행 명령어: {' '.join(cmd)}")
    
    try:
        # uvicorn 실행
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ 앱 실행 실패: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("👋 앱이 종료되었습니다.")
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()