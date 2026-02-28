import os
import uuid
from flask import Flask, render_template, request, jsonify, send_file, after_this_request
import yt_dlp

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] += os.pathsep + CURRENT_DIR

app = Flask(__name__)

if not os.path.exists('downloads'):
    os.makedirs('downloads')

# إعدادات تخطي الحظر باستخدام الكوكيز الخاصة بك
YDL_BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'cookiefile': 'cookies.txt', 
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    data = request.get_json()
    url = data.get('url')

    if not url:
        return jsonify({'error': 'Please provide a valid URL'}), 400

    try:
        with yt_dlp.YoutubeDL(YDL_BASE_OPTS) as ydl:
            # استخراج المعلومات بدون تحميل لمعاينة الفيديو
            info = ydl.extract_info(url, download=False)
            
            preview_url = None
            preview_type = 'video'
            
            # معالجة مشغلات الفيديو (تيك توك ويوتيوب)
            if 'tiktok.com' in url.lower():
                video_id = info.get('id')
                preview_url = f"https://www.tiktok.com/embed/v2/{video_id}"
                preview_type = 'iframe'
            elif 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
                video_id = info.get('id')
                preview_url = f"https://www.youtube.com/embed/{video_id}"
                preview_type = 'iframe'
            else:
                preview_url = info.get('url')

            # الاعتماد على زر واحد يدمج أفضل صوت وصورة عبر FFmpeg
            formats = [{
                'id': 'best',
                'resolution': 'تحميل أفضل جودة (MP4)',
                'ext': 'mp4',
                'url': f'/download_video?url={url}'
            }]

            return jsonify({
                'title': info.get('title', 'Video Downloader'),
                'thumbnail': info.get('thumbnail'),
                'preview_url': preview_url, 
                'preview_type': preview_type,
                'formats': formats
            })
            
    except Exception as e:
        return jsonify({'error': f"يوتيوب يرفض الرابط: {str(e)}"}), 500

@app.route('/download_video')
def download_video():
    url = request.args.get('url')
    
    file_id = str(uuid.uuid4())
    filepath = os.path.join('downloads', f"{file_id}.%(ext)s")
    
    dl_opts = dict(YDL_BASE_OPTS)
    
    # السر هنا: إجبار FFmpeg على دمج أفضل فيديو وأفضل صوت في ملف واحد
    dl_opts.update({
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': filepath,
        'merge_output_format': 'mp4',
    })
    
    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.download([url])
        
        final_filepath = None
        for file in os.listdir('downloads'):
            if file.startswith(file_id):
                final_filepath = os.path.join('downloads', file)
                break
                
        if not final_filepath:
            return "Download failed.", 500
        
        # التنظيف الذاتي للسيرفر
        @after_this_request
        def remove_file(response):
            try:
                if os.path.exists(final_filepath):
                    os.remove(final_filepath)
            except:
                pass
            return response

        return send_file(final_filepath, as_attachment=True, download_name="Video_Pro.mp4")
        
    except Exception as e:
        return f"حدث خطأ أثناء التحميل: {str(e)}", 500

if __name__ == '__main__':
    # تشغيل السيرفر محلياً (عند التجربة على الكمبيوتر)
    app.run(debug=True, port=5000)
