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
