FROM python:3.10-slim

# تحديث النظام وتثبيت FFmpeg لدمج الفيديوهات
RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app

# إصلاح خطأ النسخ
COPY . /app

# تثبيت المكتبات المطلوبة
RUN pip install --no-cache-dir -r requirements.txt

# تشغيل السيرفر باستخدام منفذ Render الديناميكي
CMD gunicorn -w 2 -b 0.0.0.0:$PORT app:app
RUN pip install --no-cache-dir -U yt-dlp

FROM python:3.11-slim

WORKDIR /app

# تثبيت ffmpeg لأن yt-dlp يحتاجه للدمج
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# نسخ الملفات
COPY requirements.txt .

# تثبيت المكتبات + أحدث yt-dlp بدون كاش
RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -U yt-dlp

COPY . .

# إنشاء مجلد التحميل
RUN mkdir -p downloads

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
