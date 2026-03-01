import os
import uuid
import re
from flask import Flask, render_template, request, jsonify, send_file, after_this_request
import yt_dlp

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] += os.pathsep + CURRENT_DIR

app = Flask(__name__)

if not os.path.exists('downloads'):
    os.makedirs('downloads')

# إعدادات بسيطة جداً لمرحلة "التحليل" فقط لتجنب أخطاء الصيغ المفقودة
YDL_BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'cookiefile': 'cookies.txt', 
}

def get_yt_id(url):
    match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11}).*', url)
    return match.group(1) if match else None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    data = request.get_json()
    url = data.get('url')

    if not url:
        return jsonify({'error': 'Please provide a valid URL'}), 400

    # الاعتماد الكلي على yt-dlp مع ملف الكوكيز (الغينا السيرفر الخارجي لأنه مزدحم ويحظرنا)
    try:
        with yt_dlp.YoutubeDL(YDL_BASE_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            
            preview_url = None
            preview_type = 'video'
            thumbnail = info.get('thumbnail', '')
            
            # العودة للمشغلات الرسمية (Iframe) لحل مشكلة الشاشة السوداء في تيك توك ويوتيوب
            if 'tiktok.com' in url.lower():
                video_id = info.get('id')
                preview_url = f"https://www.tiktok.com/embed/v2/{video_id}"
                preview_type = 'iframe'
            elif 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
                video_id = info.get('id') or get_yt_id(url)
                preview_url = f"https://www.youtube.com/embed/{video_id}" if video_id else None
                preview_type = 'iframe'
            else:
                # محاولة جلب فيديو مباشر لباقي المنصات
                formats_list = info.get('formats', [])
                for f in reversed(formats_list):
                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                        preview_url = f.get('url')
                        break

            formats = [{
                'id': 'best',
                'resolution': '⬇️ تحميل أفضل جودة (MP4)',
                'ext': 'mp4',
                'url': f'/download_video?url={url}'
            }]

            return jsonify({
                'title': info.get('title', 'Video Ready'),
                'thumbnail': thumbnail,
                'preview_url': preview_url,
                'preview_type': preview_type,
                'formats': formats
            })
    except Exception as e:
        return jsonify({'error': f"فشل التحليل، تأكد من الرابط أو الكوكيز: {str(e)}"}), 500

@app.route('/download_video')
def download_video():
    url = request.args.get('url')
    file_id = str(uuid.uuid4())
    filepath = os.path.join('downloads', f"{file_id}.%(ext)s")
    
    dl_opts = dict(YDL_BASE_OPTS)
    
    # هنا فقط نجبر الأداة على الدمج والتنزيل بصيغة تدعم الويندوز
    dl_opts.update({
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
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
        
        @after_this_request
        def remove_file(response):
            try:
                if os.path.exists(final_filepath):
                    os.remove(final_filepath)
            except:
                pass
            return response

        return send_file(final_filepath, as_attachment=True, download_name="Video.mp4")
        
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
