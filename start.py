import os 
import uvicorn 
 
try: 
    port = int(os.environ.get("PORT", 8000)) 
except: 
    port = 8000 
 
uvicorn.run("clean_news_automation:app", host="0.0.0.0", port=port) 
