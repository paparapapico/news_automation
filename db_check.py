# db_check.py 파일 생성
import sqlite3

def check_database():
    try:
        conn = sqlite3.connect("news_automation.db")
        cursor = conn.cursor()
        
        # 테이블 목록 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print("📊 데이터베이스 테이블:")
        for table in tables:
            print(f"  - {table[0]}")
            
        conn.close()
        print("✅ 데이터베이스 연결 성공!")
        
    except Exception as e:
        print(f"❌ 데이터베이스 오류: {e}")

if __name__ == "__main__":
    check_database()