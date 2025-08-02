FROM python:3.11-slim 
 
WORKDIR /app 
 
# Install system dependencies 
RUN apt-get update && apt-get install -y \ 
    ffmpeg \ 
    libsm6 \ 
    libxext6 \ 
    libfontconfig1 \ 
    libxrender1 \ 
    libgl1-mesa-glx \ 
    && rm -rf /var/lib/apt/lists/* 
 
COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt 
 
COPY . . 
 
EXPOSE 8000 
 
CMD ["uvicorn", "clean_news_automation:app", "--host", "0.0.0.0", "--port", "8000"] 
