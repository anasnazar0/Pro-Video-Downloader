# استخدام بيئة بايثون خفيفة
FROM python:3.10-slim

# تحديث النظام وتثبيت FFmpeg الأساسي من جذور النظام لضمان عمل يوتيوب
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# تحديد مجلد العمل
WORKDIR /app

# نسخ ملف المكتبات وتثبيته بشكل نظيف (بدون أخطاء buildCommand)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع (مثل app.py و index.html)
COPY . .

# أمر تشغيل السيرفر
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
