import os
import re
import time
import uuid
import threading
import logging
from pathlib import Path

from flask import Flask, request, jsonify, send_file, render_template
import yt_dlp
import imageio_ffmpeg

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

MAX_AGE_SECONDS = 2 * 60 * 60          # 2 hours
CLEANUP_INTERVAL_SECONDS = 10 * 60     # 10 minutes

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO,
format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Background cleanup daemon
# ---------------------------------------------------------------------------

def _cleanup_loop():
"""Permanently delete files in downloads/ older than MAX_AGE_SECONDS."""
while True:
try:
now = time.time()
for p in DOWNLOAD_DIR.iterdir():
if p.is_file() and (now - p.stat().st_mtime) > MAX_AGE_SECONDS:
p.unlink(missing_ok=True)
logger.info("Cleanup: deleted %s", p.name)
except Exception as exc:
logger.warning("Cleanup error: %s", exc)
time.sleep(CLEANUP_INTERVAL_SECONDS)


threading.Thread(target=_cleanup_loop, daemon=True).start()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAFE = re.compile(r'[^A-Za-z0-9_\-.]')


def _safe_filename(title: str, ext: str = "mp4") -> str:
"""Return a filesystem-safe filename with a short UUID suffix."""
base = _SAFE.sub("_", title)[:80]
short_id = uuid.uuid4().hex[:8]
return f"{base}_{short_id}.{ext}"


def _remux_to_mp4(src: str, dst: str):
"""Re-mux *src* into an mp4 container with faststart using FFmpeg."""
import subprocess
cmd = [
FFMPEG_PATH,
"-y",
"-i", src,
"-c", "copy",
"-movflags", "+faststart",
dst,
]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
if result.returncode != 0:
raise RuntimeError(f"FFmpeg failed: {result.stderr[-500:]}")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
return render_template("index.html")


@app.route("/download", methods=["POST"])
def download():
data = request.get_json(silent=True) or {}
url = (data.get("url") or "").strip()
if not url:
return jsonify({"error": "No URL provided."}), 400

# Unique temp name to avoid collisions
temp_id = uuid.uuid4().hex[:10]
temp_template = str(DOWNLOAD_DIR / f"tmp_{temp_id}.%(ext)s")

ydl_opts = {
        # Broad format fallback: prefer mp4 streams → any merged → single best
"format": (
"bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
"bestvideo[ext=mp4]+bestaudio/"
"bestvideo+bestaudio/"
"best[ext=mp4]/"
"best"
),
        "format_sort": ["vcodec:h264"],
"outtmpl": temp_template,
"merge_output_format": "mp4",
"quiet": True,
@@ -112,21 +112,16 @@
"socket_timeout": 30,
"retries": 5,
"fragment_retries": 5,
        "http_chunk_size": 10485760,           # 10 MB chunks
        "http_chunk_size": 10485760,
"ffmpeg_location": FFMPEG_PATH,
        # Pretend to be a real browser
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        # YouTube-specific: use the web client for better compatibility
        # إضافة الكوكيز لتخطي حظر يوتيوب (Bot Protection)
        "cookiefile": "cookies.txt" if os.path.exists("cookies.txt") else None,
        
        "impersonate": ImpersonateTarget(client="chrome"),
"extractor_args": {
"youtube": {
                "player_client": ["web"],
                # استخدام عملاء متعددين لتجاوز الحماية
                "player_client": ["android", "web", "ios"], 
},
},
}
@@ -218,3 +213,4 @@
serve(app, host="0.0.0.0", port=port, threads=4)
except ImportError:
app.run(host="0.0.0.0", port=port, debug=True)
