#!/usr/bin/env python3
"""
Chivet-kh Video Grab — local server (yt-dlp)
---------------------------------------------
* Serves the phone app (index.html) at  http://<PC-IP>:8800
* Exposes a cobalt-compatible API:  POST /  {url, videoQuality, downloadMode, audioFormat}
* Streams finished files at        GET /file/<name>   (Range supported, for video preview)

Setup:
    pip install -U yt-dlp
    (optional, recommended) install ffmpeg  -> merges HD video+audio, converts MP3
Run:
    python server.py            # port 8800
    python server.py 9000       # custom port
Then open the printed LAN address on your phone (same WiFi).
"""
import json
import mimetypes
import os
import re
import shutil
import socket
import sys
import threading
import time
import html
import http.cookiejar
import subprocess
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import yt_dlp
except ImportError:
    print("❌ yt-dlp មិនទាន់ដំឡើង។ សូម Run:  pip install -U yt-dlp")
    sys.exit(1)

VERSION = "1.0"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8800))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_FILE = os.path.join(BASE_DIR, "index.html")
DL_DIR = os.path.join(BASE_DIR, "downloads")
# Cloud mode (Render / Hugging Face / VG_CLOUD=1): public server like savefrom
IS_CLOUD = bool(os.environ.get("VG_CLOUD") or os.environ.get("RENDER") or os.environ.get("SPACE_ID"))
KEEP_HOURS = 1 if IS_CLOUD else 24   # auto-delete files older than this
MAX_JOBS = int(os.environ.get("VG_MAX_JOBS", 2 if IS_CLOUD else 4))   # parallel downloads
MAX_FILESIZE = 700 * 1024 * 1024 if IS_CLOUD else None
# optional cookies.txt (Netscape format) for private / login-only videos.
# On Render add it as a Secret File named cookies.txt  (-> /etc/secrets/cookies.txt). Never commit it.
COOKIES = next((c for c in (os.environ.get("VG_COOKIES_FILE", ""), "/etc/secrets/cookies.txt",
                            os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")) if c and os.path.isfile(c)), "")
# Render secret files are read-only, but yt-dlp writes cookies back -> use a writable copy
if COOKIES and COOKIES.startswith("/etc/secrets/"):
    try:
        shutil.copy(COOKIES, "/tmp/cookies.txt")
        COOKIES = "/tmp/cookies.txt"
    except OSError:
        pass
_jobs = threading.BoundedSemaphore(MAX_JOBS)
HAS_FFMPEG = shutil.which("ffmpeg") is not None
API_KEY = os.environ.get("VG_API_KEY", "")   # optional: set to require "Authorization: Api-Key <key>"

# Running on Android (Termux)? Save straight into the phone's Download/VideoGrab folder
IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")
PHONE_DL = os.path.expanduser("~/storage/downloads")
SAVED_TO = ""
if os.environ.get("VG_DIR"):
    DL_DIR = os.environ["VG_DIR"]
elif IS_TERMUX and os.path.isdir(PHONE_DL):
    DL_DIR = os.path.join(PHONE_DL, "VideoGrab")
    SAVED_TO = "Download/VideoGrab"
    KEEP_HOURS = 0                   # never auto-delete the user's saved videos

os.makedirs(DL_DIR, exist_ok=True)
_lock = threading.Lock()


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def cleanup_old():
    if KEEP_HOURS <= 0:
        return
    cutoff = time.time() - KEEP_HOURS * 3600
    for f in os.listdir(DL_DIR):
        p = os.path.join(DL_DIR, f)
        try:
            if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass


def build_opts(quality, mode, audio_format):
    h = "" if quality in ("max", "", None) else f"[height<={int(quality)}]"
    opts = {
        "outtmpl": os.path.join(DL_DIR, "%(title).70B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": False,
        "windowsfilenames": True,
        "concurrent_fragment_downloads": 4,
        "retries": 3,
    }
    if MAX_FILESIZE:
        opts["max_filesize"] = MAX_FILESIZE
    if COOKIES:
        opts["cookiefile"] = COOKIES
    if mode == "audio":
        opts["format"] = "bestaudio/best"
        if HAS_FFMPEG and audio_format in ("mp3", "opus", "wav"):
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
                "preferredquality": "192",
            }]
    elif mode == "mute":
        opts["format"] = f"bestvideo{h}[ext=mp4]/bestvideo{h}/best{h}/best"
    else:
        if HAS_FFMPEG:
            opts["format"] = (f"bestvideo{h}[vcodec^=avc1]+bestaudio[ext=m4a]/"
                              f"bestvideo{h}[ext=mp4]+bestaudio[ext=m4a]/"
                              f"bestvideo{h}+bestaudio/best{h}/best")
            opts["merge_output_format"] = "mp4"
        else:
            # without ffmpeg only pre-merged formats work (usually max 720p on YouTube)
            opts["format"] = f"best{h}[ext=mp4]/best{h}/best"
    return opts


def run_download(url, quality, mode, audio_format):
    opts = build_opts(quality, mode, audio_format)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info.get("_type") == "playlist" and info.get("entries"):
            info = next(e for e in info["entries"] if e)
        path = None
        rd = info.get("requested_downloads") or []
        if rd and rd[-1].get("filepath"):
            path = rd[-1]["filepath"]
        if not path or not os.path.exists(path):
            path = ydl.prepare_filename(info)
            if mode == "audio" and opts.get("postprocessors"):
                path = os.path.splitext(path)[0] + "." + audio_format
            elif opts.get("merge_output_format"):
                path = os.path.splitext(path)[0] + ".mp4"
        if not os.path.exists(path):
            raise RuntimeError("file not found after download")
        return os.path.basename(path)


# ---------------- Facebook fallback (when yt-dlp can't parse the page) ----------------
FB_RE = re.compile(r"(facebook\.com|fb\.watch|fb\.com)", re.I)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
FB_HD = [r'"browser_native_hd_url":"([^"]+)"', r'"playable_url_quality_hd":"([^"]+)"',
         r'"hd_src(?:_no_ratelimit)?":"([^"]+)"', r'hd_src(?:_no_ratelimit)?:"([^"]+)"']
FB_SD = [r'"browser_native_sd_url":"([^"]+)"', r'"playable_url":"([^"]+)"',
         r'"sd_src(?:_no_ratelimit)?":"([^"]+)"', r'sd_src(?:_no_ratelimit)?:"([^"]+)"']


def _fb_opener():
    jar = http.cookiejar.MozillaCookieJar()
    if COOKIES:
        try:
            jar.load(COOKIES, ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", UA),
                     ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
                     ("Accept-Language", "en-US,en;q=0.9"),
                     ("Sec-Fetch-Mode", "navigate"), ("Sec-Fetch-Site", "none"), ("Sec-Fetch-Dest", "document")]
    return op


def _unescape(u):
    try:
        u = json.loads('"' + u + '"')
    except Exception:
        u = u.replace("\\/", "/")
    return html.unescape(u)


def fb_find_video(page, quality):
    order = (FB_HD + FB_SD) if quality in ("max", "1080", "720") else (FB_SD + FB_HD)
    for pat in order:
        m = re.search(pat, page)
        if m:
            return _unescape(m.group(1))
    return None


def fb_title(page):
    for pat in (r'<meta property="og:title" content="([^"]{1,200})"', r'<title>([^<]{1,200})</title>'):
        m = re.search(pat, page)
        if m:
            t = html.unescape(m.group(1)).strip()
            if t and t.lower() not in ("facebook", "log in or sign up to view", "log into facebook"):
                return t
    return "facebook_video"


def safe_name(t):
    t = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", t).strip()[:70].strip() or "video"
    return t


def fb_fallback(url, quality, mode, audio_format):
    op = _fb_opener()
    page = op.open(url, timeout=30).read().decode("utf-8", "ignore")
    vurl = fb_find_video(page, quality)
    if not vurl:
        raise RuntimeError("Facebook: no video URL in page (video may be private or login required)")
    m = re.search(r"/(?:videos|reel|v)/(\d+)|[?&]v=(\d+)", url)
    vid = (m.group(1) or m.group(2)) if m else str(int(time.time()))
    base = os.path.join(DL_DIR, f"{safe_name(fb_title(page))} [{vid}]")
    mp4 = base + ".mp4"
    with op.open(urllib.request.Request(vurl, headers={"Referer": "https://www.facebook.com/"}), timeout=60) as r, \
            open(mp4 + ".part", "wb") as f:
        shutil.copyfileobj(r, f, 256 * 1024)
    os.replace(mp4 + ".part", mp4)
    if mode in ("audio", "mute") and HAS_FFMPEG:
        if mode == "audio":
            ext = audio_format if audio_format in ("mp3", "opus", "wav") else "m4a"
            out = base + "." + ext
            args = ["-vn"] + (["-c:a", "copy"] if ext == "m4a" else ["-b:a", "192k"])
        else:
            out = base + " (mute).mp4"
            args = ["-an", "-c:v", "copy"]
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp4, *args, out], check=True)
        os.remove(mp4)
        return os.path.basename(out)
    return os.path.basename(mp4)


def download_any(url, quality, mode, audio_format):
    try:
        return run_download(url, quality, mode, audio_format)
    except Exception as e:
        if not FB_RE.search(url):
            raise
        print("↪️  yt-dlp failed, trying Facebook fallback:", str(e)[:120])
        try:
            return fb_fallback(url, quality, mode, audio_format)
        except Exception as e2:
            raise RuntimeError(f"{e}  |  fallback: {e2}")


def classify_error(msg):
    m = msg.lower()
    if "unsupported url" in m:
        return "error.api.link.unsupported"
    if "private" in m or "login" in m or "sign in" in m or "age" in m:
        return "error.api.content.video.private"
    if "unavailable" in m or "404" in m or "removed" in m:
        return "error.api.content.video.unavailable"
    if "429" in m or "too many" in m:
        return "error.api.rate_exceeded"
    return "error.api.fetch.fail"


class Handler(BaseHTTPRequestHandler):
    server_version = "ChivetVideoGrab/" + VERSION

    # ---------- helpers ----------
    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Authorization, Range")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range, Content-Disposition")
        # allow pages hosted on https (e.g. GitHub Pages) to reach this local server
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        if not API_KEY:
            return True
        return self.headers.get("Authorization", "") == "Api-Key " + API_KEY

    def log_message(self, fmt, *args):
        sys.stdout.write("  %s  %s\n" % (self.address_string(), fmt % args))

    # ---------- methods ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            return self.send_json({"ok": True})
        if path in ("/", "/index.html"):
            accept = self.headers.get("Accept", "")
            if "text/html" in accept and os.path.exists(APP_FILE):
                return self.serve_file(APP_FILE, inline=True, ctype="text/html; charset=utf-8")
            return self.send_json({"server": "chivet-video-grab", "version": VERSION,
                                   "ffmpeg": HAS_FFMPEG, "yt_dlp": yt_dlp.version.__version__})
        if path.startswith("/file/"):
            name = os.path.basename(urllib.parse.unquote(path[len("/file/"):]))
            full = os.path.join(DL_DIR, name)
            if not name or not os.path.isfile(full):
                return self.send_json({"error": "not found"}, 404)
            return self.serve_file(full, inline=False)
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/":
            return self.send_json({"error": "not found"}, 404)
        if not self.authorized():
            return self.send_json({"status": "error", "error": {"code": "error.api.auth.key.invalid"}}, 401)
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self.send_json({"status": "error", "error": {"code": "error.api.invalid_body"}}, 400)

        url = str(body.get("url", "")).strip()
        if not re.match(r"^https?://", url):
            return self.send_json({"status": "error", "error": {"code": "error.api.link.invalid"}}, 400)
        quality = str(body.get("videoQuality", "720"))
        if quality != "max" and not quality.isdigit():
            quality = "720"
        mode = body.get("downloadMode", "auto")
        audio_format = body.get("audioFormat", "mp3")

        print(f"⬇️  {mode} {quality}  {url}")
        try:
            cleanup_old()
            if not _jobs.acquire(timeout=120):
                return self.send_json({"status": "error", "error": {"code": "error.api.rate_exceeded",
                                       "context": {"message": "server busy"}}})
            try:
                name = download_any(url, quality, mode, audio_format)
            finally:
                _jobs.release()
        except Exception as e:
            msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
            print("❌ ", msg)
            return self.send_json({"status": "error",
                                   "error": {"code": classify_error(msg), "context": {"message": msg[:300]}}})
        host = self.headers.get("Host") or f"{lan_ip()}:{PORT}"
        scheme = (self.headers.get("X-Forwarded-Proto") or "http").split(",")[0].strip()
        file_url = f"{scheme}://{host}/file/{urllib.parse.quote(name)}"
        print("✅ ", name)
        res = {"status": "tunnel", "url": file_url, "filename": name}
        if SAVED_TO:
            res["saved_to"] = SAVED_TO
        self.send_json(res)

    # ---------- file streaming with Range ----------
    def serve_file(self, full, inline=False, ctype=None):
        size = os.path.getsize(full)
        ctype = ctype or mimetypes.guess_type(full)[0] or "application/octet-stream"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        partial = False
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                elif m.group(2):
                    start = max(0, size - int(m.group(2)))
                partial = start <= end
        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if not inline:
            fname = os.path.basename(full)
            ascii_name = re.sub(r'[^A-Za-z0-9._ -]', "_", fname)
            self.send_header("Content-Disposition",
                             f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{urllib.parse.quote(fname)}")
        self.end_headers()
        try:
            with open(full, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    ip = lan_ip()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("=" * 52)
    print("  Chivet-kh Video Grab Server  v" + VERSION)
    print("=" * 52)
    if IS_CLOUD:
        print(f"  ☁️  Cloud mode · port {PORT} · keep files {KEEP_HOURS}h · max jobs {MAX_JOBS}")
        print(f"  🍪 cookies: {'yes' if COOKIES else 'no'}")
    elif IS_TERMUX:
        print(f"  📱 បើក Chrome លើទូរស័ព្ទនេះ:  http://127.0.0.1:{PORT}")
        if not SAVED_TO:
            print("  ⚠️  Run  termux-setup-storage  ដើម្បីរក្សាវិដេអូចូល Download/VideoGrab")
    else:
        print(f"  📱 បើកលើទូរស័ព្ទ (WiFi តែមួយ):  http://{ip}:{PORT}")
        print(f"  💻 បើកលើ PC:                   http://127.0.0.1:{PORT}")
    print(f"  📁 ឯកសារទុកក្នុង:  {DL_DIR}")
    print(f"  🎞  ffmpeg: {'មាន ✅ (HD + MP3)' if HAS_FFMPEG else 'គ្មាន ⚠️  (ទាញបានតែ format រួម ~720p)'}")
    if API_KEY:
        print("  🔑 API Key: required")
    if not os.path.exists(APP_FILE):
        print("  ⚠️  រកមិនឃើញ index.html — ដាក់វានៅ Folder ជាមួយ server.py")
    print("  ចុច Ctrl+C ដើម្បីបិទ")
    print("=" * 52)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 បានបិទ Server")


if __name__ == "__main__":
    main()
