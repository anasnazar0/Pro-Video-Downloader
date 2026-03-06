FROM python:3.11-slim

# منع بايثون من كتابة ملفات التخزين المؤقت وتفعيل إخراج السجلات فوراً
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# تثبيت FFmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# تثبيت المكتبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي الملفات
COPY . .

# إنشاء مجلد التنزيلات وإعطائه صلاحيات الكتابة الكاملة لتجنب أي توقف
RUN mkdir -p downloads && chmod 777 downloads

# (تم حذف ENV PORT=5000 و EXPOSE لكي نترك Render تتحكم بالمنفذ ديناميكياً)

# تشغيل السيرفر
CMD ["python", "app.py"]
