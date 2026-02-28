FROM python:3.10-slim

# تحديث النظام وتثبيت FFmpeg
RUN apt-get update && apt-get install -y ffmpeg

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Render يستخدم المنفذ 10000 افتراضياً
EXPOSE 10000

# أمر التشغيل الاحترافي
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:10000", "app:app"]

