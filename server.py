"""
Exyplay Music Server
Flask REST API wrapping ytmusicapi for the Exyplay Android app.
Run: python server.py
"""

import os
import sys
import shutil
import logging
import subprocess
import time
import requests
from functools import wraps

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("exyplay")

# ════════════════════════════════════════════════════════════════════════════
# 1. SETUP SYSTEM DEPENDENCIES (MUST HAPPEN BEFORE IMPORTING YT-DLP)
# ════════════════════════════════════════════════════════════════════════════

def setup_environment():
    """Sets up Node.js and builds the official PO Token Provider"""
    node_dir = "/tmp/nodejs"
    node_bin = os.path.join(node_dir, "bin", "node")
    npm_bin = os.path.join(node_dir, "bin", "npm")
    tsc_bin = os.path.join(node_dir, "bin", "tsc")
    
    # 1. Install Node.js (Required for YouTube JS signatures & Token Server)
    if not os.path.exists(node_bin):
        log.info("Downloading Node.js...")
        subprocess.run("curl -sL https://nodejs.org/dist/v20.11.1/node-v20.11.1-linux-x64.tar.xz | tar xJ -C /tmp", shell=True)
        if os.path.exists("/tmp/node-v20.11.1-linux-x64"):
            shutil.move("/tmp/node-v20.11.1-linux-x64", node_dir)
            
    # Update PATH immediately before any other imports
    os.environ["PATH"] = f"{os.path.join(node_dir, 'bin')}:{os.environ.get('PATH', '')}"

    try:
        subprocess.run([node_bin, "-v"], check=True, stdout=subprocess.DEVNULL)
        log.info("✅ Node.js is ready in system PATH.")
    except Exception as e:
        log.error(f"❌ Node.js failed: {e}")

    # 2. Clone and build the official Brainicism PO Token server
    bgutil_repo = "/tmp/bgutil-repo"
    server_dir = os.path.join(bgutil_repo, "server")
    main_js = os.path.join(server_dir, "build", "main.js")
    
    if not os.path.exists(main_js):
        log.info("Cloning official bgutil repository...")
        if os.path.exists(bgutil_repo):
            shutil.rmtree(bgutil_repo)
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git", bgutil_repo], check=True)
        
        log.info("Installing NPM dependencies...")
        # Render sets NODE_ENV=production, which ignores devDependencies like TypeScript
        # We use --include=dev to force npm to install everything needed to build
        subprocess.run([npm_bin, "install", "--include=dev"], cwd=server_dir, check=True)
        
        log.info("Installing TypeScript globally to avoid npx conflicts...")
        subprocess.run([npm_bin, "install", "-g", "typescript"], check=True)
        
        log.info("Building TypeScript to JavaScript...")
        # Use the global tsc compiler directly, skipping npx
        subprocess.run([tsc_bin], cwd=server_dir, check=True)

    # 3. Start the background HTTP server
    try:
        requests.get("http://127.0.0.1:4416/ping", timeout=1)
        log.info("✅ bgutil-pot server is already running.")
        return
    except:
        pass

    log.info("Starting official bgutil HTTP server on port 4416...")
    subprocess.Popen(
        [node_bin, main_js, "server", "--port", "4416"],
        stdout=sys.stdout, stderr=sys.stderr
    )
    
    for i in range(15):
        try:
            requests.get("http://127.0.0.1:4416/ping", timeout=1)
            log.info("✅ bgutil PO Token server is ready and responding!")
            return
        except:
            time.sleep(1)
            
    log.error("❌ bgutil PO Token server failed to start.")

# EXECUTE SETUP BEFORE IMPORTING YT-DLP
setup_environment()

import yt_dlp
from flask import Flask, request, jsonify
from flask_cors import CORS
from ytmusicapi import YTMusic

# ════════════════════════════════════════════════════════════════════════════
# 2. APP INITIALIZATION
# ════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
CORS(app)

class YTDLLogger(object):
    def debug(self, msg): log.info(f"YT-DLP-DEBUG: {msg}")
    def warning(self, msg): log.warning(f"YT-DLP-WARN: {msg}")
    def error(self, msg): log.error(f"YT-DLP-ERROR: {msg}")

AUTH_FILE = os.getenv("YTMUSIC_AUTH_FILE", "browser.json")

def _get_ytmusic(auth=True):
    if auth and os.path.exists(AUTH_FILE):
        return YTMusic(AUTH_FILE, language="en")
    return YTMusic(language="en")

_ytm_public = _get_ytmusic(auth=False)
_ytm_auth   = None   

def get_ytm(needs_auth=False):
    global _ytm_auth
    if needs_auth:
        if _ytm_auth is None:
            _ytm_auth = _get_ytmusic(auth=True)
        return _ytm_auth
    return _ytm_public

def ok(data): return jsonify({"status": "ok", "data": data})
def err(msg, code=400): return jsonify({"status": "error", "message": str(msg)}), code

def handle(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log.exception("Request failed")
            return err(str(e), 500)
    return wrapper

def qp(name, default=None): return request.args.get(name, default)
def qpi(name, default=None):
    v = request.args.get(name)
    return int(v) if v is not None else default
def qpb(name, default=False):
    v = request.args.get(name, "").lower()
    if v in ("1", "true", "yes"): return True
    if v in ("0", "false", "no"): return False
    return default

# ════════════════════════════════════════════════════════════════════════════
# 3. YTMUSIC ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════

@app.route("/search")
@handle
def search():
    query = qp("q")
    if not query: return err("Missing query param: q")
    return ok(get_ytm().search(query=query, filter=qp("filter"), limit=qpi("limit", 20), ignore_spelling=qpb("ignore_spelling")))

@app.route("/search/suggestions")
@handle
def search_suggestions():
    query = qp("q")
    if not query: return err("Missing query param: q")
    return ok(get_ytm().get_search_suggestions(query=query, detailed_runs=qpb("detailed")))

@app.route("/home")
@handle
def home(): return ok(get_ytm().get_home(limit=qpi("limit", 6)))

@app.route("/artist/<channel_id>")
@handle
def get_artist(channel_id): return ok(get_ytm().get_artist(channel_id))

@app.route("/artist/<channel_id>/albums")
@handle
def get_artist_albums(channel_id):
    params = qp("params")
    if not params: return err("Missing query param: params")
    return ok(get_ytm().get_artist_albums(channel_id, params=params))

@app.route("/album/<browse_id>")
@handle
def get_album(browse_id): return ok(get_ytm().get_album(browse_id))

@app.route("/album/<browse_id>/browse-id")
@handle
def get_album_browse_id(browse_id): return ok(get_ytm().get_album_browse_id(browse_id))

@app.route("/user/<channel_id>")
@handle
def get_user(channel_id): return ok(get_ytm().get_user(channel_id))

@app.route("/user/<channel_id>/playlists")
@handle
def get_user_playlists(channel_id): return ok(get_ytm().get_user_playlists(channel_id, params=qp("params")))

@app.route("/song/<video_id>")
@handle
def get_song(video_id): return ok(get_ytm().get_song(video_id))

@app.route("/song/<video_id>/related")
@handle
def get_song_related(video_id): return ok(get_ytm().get_song_related(browse_id=video_id))

@app.route("/lyrics/<browse_id>")
@handle
def get_lyrics(browse_id): return ok(get_ytm().get_lyrics(browse_id))

@app.route("/tasteprofile")
@handle
def get_tasteprofile(): return ok(get_ytm().get_tasteprofile())

@app.route("/explore/moods")
@handle
def get_mood_categories(): return ok(get_ytm().get_mood_categories())

@app.route("/explore/mood-playlists")
@handle
def get_mood_playlists():
    params = qp("params")
    if not params: return err("Missing query param: params")
    return ok(get_ytm().get_mood_playlists(params))

@app.route("/explore/charts")
@handle
def get_charts(): return ok(get_ytm().get_charts(country=qp("country", "ZZ")))

@app.route("/watch")
@handle
def get_watch_playlist():
    video_id, playlist_id = qp("videoId"), qp("playlistId")
    if not video_id and not playlist_id: return err("Provide at least videoId or playlistId")
    return ok(get_ytm().get_watch_playlist(videoId=video_id, playlistId=playlist_id, limit=qpi("limit", 25), radio=qpb("radio"), shuffle=qpb("shuffle")))

@app.route("/playlist/<playlist_id>")
@handle
def get_playlist(playlist_id): return ok(get_ytm().get_playlist(playlist_id, limit=qpi("limit")))

@app.route("/playlist/<playlist_id>/suggestions")
@handle
def get_playlist_suggestions(playlist_id): return ok(get_ytm().get_playlist_suggestions(playlist_id))

@app.route("/playlist", methods=["POST"])
@handle
def create_playlist():
    body = request.get_json(force=True)
    return ok(get_ytm(needs_auth=True).create_playlist(title=body["title"], description=body.get("description", ""), privacy_status=body.get("privacy_status", "PRIVATE"), video_ids=body.get("video_ids"), source_playlist=body.get("source_playlist")))

@app.route("/playlist/<playlist_id>", methods=["PUT"])
@handle
def edit_playlist(playlist_id):
    body = request.get_json(force=True)
    return ok(get_ytm(needs_auth=True).edit_playlist(playlistId=playlist_id, title=body.get("title"), description=body.get("description"), privacyStatus=body.get("privacy_status")))

@app.route("/playlist/<playlist_id>", methods=["DELETE"])
@handle
def delete_playlist(playlist_id): return ok(get_ytm(needs_auth=True).delete_playlist(playlist_id))

@app.route("/playlist/<playlist_id>/tracks", methods=["POST"])
@handle
def add_playlist_items(playlist_id):
    body = request.get_json(force=True)
    return ok(get_ytm(needs_auth=True).add_playlist_items(playlistId=playlist_id, videoIds=body.get("video_ids"), source_playlist=body.get("source_playlist"), duplicates=body.get("duplicates", False)))

@app.route("/playlist/<playlist_id>/tracks", methods=["DELETE"])
@handle
def remove_playlist_items(playlist_id):
    body = request.get_json(force=True)
    return ok(get_ytm(needs_auth=True).remove_playlist_items(playlist_id, body["tracks"]))

@app.route("/playlist/<playlist_id>/tracks/move", methods=["POST"])
@handle
def move_playlist_item(playlist_id):
    body = request.get_json(force=True)
    return ok(get_ytm(needs_auth=True).move_playlist_item(playlistId=playlist_id, setVideoId=body["set_video_id"], moveSetVideoIdSuccessor=body.get("move_set_video_id_successor")))

@app.route("/library/playlists")
@handle
def get_library_playlists(): return ok(get_ytm(needs_auth=True).get_library_playlists(limit=qpi("limit", 25)))

@app.route("/library/songs")
@handle
def get_library_songs(): return ok(get_ytm(needs_auth=True).get_library_songs(limit=qpi("limit", 25), order=qp("order")))

@app.route("/library/albums")
@handle
def get_library_albums(): return ok(get_ytm(needs_auth=True).get_library_albums(limit=qpi("limit", 25), order=qp("order")))

@app.route("/library/artists")
@handle
def get_library_artists(): return ok(get_ytm(needs_auth=True).get_library_artists(limit=qpi("limit", 25), order=qp("order")))

@app.route("/library/subscriptions")
@handle
def get_library_subscriptions(): return ok(get_ytm(needs_auth=True).get_library_subscriptions(limit=qpi("limit", 25)))

@app.route("/library/podcasts")
@handle
def get_library_podcasts(): return ok(get_ytm(needs_auth=True).get_library_podcasts(limit=qpi("limit", 25)))

@app.route("/library/channels")
@handle
def get_library_channels(): return ok(get_ytm(needs_auth=True).get_library_channels(limit=qpi("limit", 25)))

@app.route("/library/history")
@handle
def get_history(): return ok(get_ytm(needs_auth=True).get_history())

@app.route("/library/history", methods=["POST"])
@handle
def add_history_item():
    body = request.get_json(force=True)
    return ok(get_ytm(needs_auth=True).add_history_item(body["song"]))

@app.route("/library/history/<video_id>", methods=["DELETE"])
@handle
def remove_history_items(video_id):
    token = qp("feedbackToken")
    if not token: return err("Missing feedbackToken query param")
    return ok(get_ytm(needs_auth=True).remove_history_items([token]))

@app.route("/rate/song", methods=["POST"])
@handle
def rate_song():
    body = request.get_json(force=True)
    return ok(get_ytm(needs_auth=True).rate_song(body["video_id"], body["rating"]))

@app.route("/rate/playlist", methods=["POST"])
@handle
def rate_playlist():
    body = request.get_json(force=True)
    return ok(get_ytm(needs_auth=True).rate_playlist(body["playlist_id"], body["rating"]))

@app.route("/subscribe", methods=["POST"])
@handle
def subscribe_artists():
    body = request.get_json(force=True)
    return ok(get_ytm(needs_auth=True).subscribe_artists(body["channel_ids"]))

@app.route("/unsubscribe", methods=["POST"])
@handle
def unsubscribe_artists():
    body = request.get_json(force=True)
    return ok(get_ytm(needs_auth=True).unsubscribe_artists(body["channel_ids"]))

@app.route("/podcast/<browse_id>")
@handle
def get_podcast(browse_id): return ok(get_ytm().get_podcast(browse_id))

@app.route("/episode/<video_id>")
@handle
def get_episode(video_id): return ok(get_ytm().get_episode(video_id))

@app.route("/channel/<channel_id>")
@handle
def get_channel(channel_id): return ok(get_ytm().get_channel(channel_id))

@app.route("/channel/<channel_id>/episodes")
@handle
def get_channel_episodes(channel_id): return ok(get_ytm().get_channel_episodes(channel_id, params=qp("params")))

@app.route("/uploads/songs")
@handle
def get_library_upload_songs(): return ok(get_ytm(needs_auth=True).get_library_upload_songs(limit=qpi("limit", 25), order=qp("order")))

@app.route("/uploads/artists")
@handle
def get_library_upload_artists(): return ok(get_ytm(needs_auth=True).get_library_upload_artists(limit=qpi("limit", 25)))

@app.route("/uploads/albums")
@handle
def get_library_upload_albums(): return ok(get_ytm(needs_auth=True).get_library_upload_albums(limit=qpi("limit", 25)))

@app.route("/uploads/artist/<artist_id>")
@handle
def get_library_upload_artist(artist_id): return ok(get_ytm(needs_auth=True).get_library_upload_artist(artist_id))

@app.route("/uploads/album/<album_id>")
@handle
def get_library_upload_album(album_id): return ok(get_ytm(needs_auth=True).get_library_upload_album(album_id))

@app.route("/uploads/song/<entity_id>", methods=["DELETE"])
@handle
def delete_upload_entity(entity_id): return ok(get_ytm(needs_auth=True).delete_upload_entity(entity_id))

# ════════════════════════════════════════════════════════════════════════════
# 4. AUDIO STREAMING & BOT BYPASS
# ════════════════════════════════════════════════════════════════════════════

@app.route("/stream/<video_id>")
@handle
def get_stream_url(video_id):
    ORIGINAL_COOKIES = os.getenv("COOKIES_FILE", "/etc/secrets/cookies.txt")
    COOKIES_FILE = "/tmp/cookies.txt"
    yt_url       = f"https://www.youtube.com/watch?v={video_id}"
    cookies_ok   = os.path.exists(ORIGINAL_COOKIES)

    if cookies_ok:
        try:
            shutil.copy(ORIGINAL_COOKIES, COOKIES_FILE)
        except Exception as e:
            log.error(f"Failed to copy cookies to /tmp: {e}")
            cookies_ok = False

    def try_ytdlp(client, use_cookies):
        opts = {
            "format":        "bestaudio/best",
            "quiet":         True, 
            "no_warnings":   True, 
            "skip_download": True,
            "extractor_args": {
                "youtube": {"player_client": [client]},
                "pot": {"bgutil": ["base_url=http://127.0.0.1:4416"]} # Explicitly tell plugin where to look
            }
        }
        
        if use_cookies and cookies_ok:
            opts["cookiefile"] = COOKIES_FILE
            
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(yt_url, download=False)
        return info.get("url", ""), info.get("ext", "webm")

    attempts = [
        ("mweb",         True),
        ("web",          True),
        ("ios",          True),
        ("tv_embedded",  False),
        ("android",      False),
    ]

    for client, use_cookies in attempts:
        label = f"{'cookies+' if use_cookies else ''}{client}"
        try:
            url, ext = try_ytdlp(client, use_cookies)
            if url:
                log.info(f"✅ {label} → {video_id} [{ext}]")
                return ok({"url": url, "ext": ext, "videoId": video_id, "source": label})
        except Exception:
            pass

    return err("Could not resolve stream. Check Render logs — run /stream/debug to diagnose.", 503)

@app.route("/stream/debug")
@handle
def stream_debug():
    test_id = "dQw4w9WgXcQ"
    results = {}
    ORIGINAL_COOKIES = os.getenv("COOKIES_FILE", "/etc/secrets/cookies.txt")
    COOKIES_FILE = "/tmp/cookies.txt"
    cookies_ok = os.path.exists(ORIGINAL_COOKIES)

    if cookies_ok:
        try:
            shutil.copy(ORIGINAL_COOKIES, COOKIES_FILE)
        except Exception:
            cookies_ok = False

    if cookies_ok:
        try:
            ydl_opts = {
                "format": "bestaudio/best", 
                "quiet": False, "no_warnings": False, "verbose": True, "logger": YTDLLogger(),
                "skip_download": True, "cookiefile": COOKIES_FILE,
                "extractor_args": {
                    "youtube": {"player_client": ["mweb"]},
                    "pot": {"bgutil": ["base_url=http://127.0.0.1:4416"]}
                }
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={test_id}", download=False)
            results["cookies+mweb"] = "✅ WORKS" if info.get("url") else "❌ empty"
        except Exception as e:
            results["cookies+mweb"] = f"❌ {str(e)[:100]}"
    else:
        results["cookies+mweb"] = f"⚠️  No cookies.txt at '{ORIGINAL_COOKIES}'"

    working = [k for k, v in results.items() if v.startswith("✅")]
    return ok({
        "test_video": test_id, "cookies_present": cookies_ok,
        "results": results, "working_methods": working
    })

@app.route("/status")
def status():
    return jsonify({"status": "ok", "server": "Exyplay Music Server", "auth_enabled": os.path.exists(AUTH_FILE)})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
