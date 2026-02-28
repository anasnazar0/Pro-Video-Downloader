import os
import uuid
import subprocess
from flask import Flask, render_template, request, jsonify, send_file, after_this_request
import yt_dlp

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] += os.pathsep + CURRENT_DIR

app = Flask(__name__)

if not os.path.exists('downloads'):
    os.makedirs('downloads')

# ==== الحل الحقيقي: إعدادات تتجاهل الأخطاء وتسحب الملف المدمج الجاهز ====
YDL_BASE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'cookiefile': 'cookies.txt',
    'ignoreerrors': True, 
    'format': 'b' 
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
            info = ydl.extract_info(url, download=False)
            
            if not info:
                 return jsonify({'error': 'Could not extract video information.'}), 400

            formats = []
            raw_formats = info.get('formats', [])
            
            preview_url = None
            preview_type = 'video'
            
            if 'tiktok.com' in url.lower():
                video_id = info.get('id')
                preview_url = f"https://www.tiktok.com/embed/v2/{video_id}"
                preview_type = 'iframe'
            else:
                raw_preview = info.get('url')
                preview_url = raw_preview
                preview_type = 'video'

            # إذا كان الفيديو Shorts أو لا يحتوي صيغ مفصلة، نعرض زراً واحداً للتحميل المباشر
            if not raw_formats:
                formats.append({
                    'id': 'b',
                    'resolution': 'Best Quality',
                    'ext': 'mp4',
                    'url': f'/download_video?url={url}&format_id=b'
                })
            else:
                # ترتيب وعرض الصيغ بطريقة لا تسبب انهيار الكود
                unique_resolutions = set()
                for f in raw_formats:
                    vcodec = f.get('vcodec', 'none')
                    if vcodec == 'none': continue 
                    
                    height = f.get('height')
                    if height:
                        res_str = f"{height}p"
                        if res_str not in unique_resolutions:
                            unique_resolutions.add(res_str)
                            formats.append({
                                'id': f.get('format_id'),
                                'resolution': res_str,
                                'ext': 'mp4',
                                'url': f'/download_video?url={url}&format_id={f.get("format_id")}'
                            })
                            
                formats.sort(key=lambda x: int(x['resolution'].replace('p','')) if 'p' in x['resolution'] else 0, reverse=True)
                formats = formats[:5] 

            return jsonify({
                'title': info.get('title', 'Video'),
                'thumbnail': info.get('thumbnail'),
                'preview_url': preview_url, 
                'preview_type': preview_type,
                'formats': formats if formats else [{'id': 'b', 'resolution': 'Best Quality', 'ext': 'mp4', 'url': f'/download_video?url={url}&format_id=b'}]
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download_video')
def download_video():
    url = request.args.get('url')
    format_id = request.args.get('format_id', 'b')
    
    file_id = str(uuid.uuid4())
    filepath = os.path.join('downloads', f"{file_id}.%(ext)s")
    
    dl_opts = dict(YDL_BASE_OPTS)
    
    if format_id == 'b':
        dl_opts['format'] = 'b'
    else:
        dl_opts['format'] = f'{format_id}+bestaudio/b'
        
    dl_opts.update({
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

        return send_file(final_filepath, as_attachment=True, download_name="video.mp4")
        
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
