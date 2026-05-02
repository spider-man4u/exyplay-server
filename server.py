"""
Exyplay Music Server
Flask REST API wrapping ytmusicapi for the Exyplay Android app.
Run: python server.py
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import shutil
import json
import logging
import subprocess
from functools import wraps
import requests
import yt_dlp

# ── ytmusicapi ──────────────────────────────────────────────────────────────
from ytmusicapi import YTMusic

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("exyplay")

# ── Verbose YT-DLP Logger ────────────────────────────────────────────────────
class YTDLLogger(object):
    def debug(self, msg):
        log.info(f"YT-DLP-DEBUG: {msg}")
    def warning(self, msg):
        log.warning(f"YT-DLP-WARN: {msg}")
    def error(self, msg):
        log.error(f"YT-DLP-ERROR: {msg}")

# ── Auto-Install Node.js & PO Token Server ──────────────────────────────────
def init_node_and_pot():
    """Downloads Node.js and runs the matched v1.3.1 PO Token server"""
    node_dir = "/tmp/nodejs"
    node_bin = os.path.join(node_dir, "bin", "node")
    
    # 1. Install Node.js if missing (yt-dlp needs this to decrypt YouTube signatures)
    if not os.path.exists(node_bin):
        log.info("Downloading Node.js (required for JS challenges)...")
        subprocess.run("curl -sL https://nodejs.org/dist/v20.11.1/node-v20.11.1-linux-x64.tar.xz | tar xJ -C /tmp", shell=True)
        if os.path.exists("/tmp/node-v20.11.1-linux-x64"):
            shutil.move("/tmp/node-v20.11.1-linux-x64", node_dir)
        log.info("Node.js installed.")

    # Add Node to PATH so yt-dlp can find it automatically
    os.environ["PATH"] = f"{os.path.join(node_dir, 'bin')}:{os.environ.get('PATH', '')}"

    # 2. Download the Rust PO Token server binary (PINNED TO 1.3.1)
    binary_path = "/tmp/bgutil-pot"
    if not os.path.exists(binary_path):
        log.info("Downloading bgutil-pot token generator v1.3.1...")
        # CRITICAL: This URL matches the pip plugin version
        url = "https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/download/v1.3.1/bgutil-pot-linux-x86_64"
        try:
            import urllib.request
            import stat
            urllib.request.urlretrieve(url, binary_path)
            st = os.stat(binary_path)
            os.chmod(binary_path, st.st_mode | stat.S_IEXEC)
            log.info("Successfully downloaded and configured bgutil-pot v1.3.1.")
        except Exception as e:
            log.error(f"Failed to download bgutil-pot: {e}")
            return

    # 3. Start the background HTTP server
    try:
        requests.get("http://127.0.0.1:4416", timeout=1)
        log.info("bgutil-pot server is already running.")
    except:
        log.info("Starting bgutil PO Token server on port 4416...")
        subprocess.Popen(
            [binary_path, "server", "--port", "4416"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        import time
        time.sleep(3) # Give server time to boot

init_node_and_pot()

# ── Auth setup ───────────────────────────────────────────────────────────────
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

# ── Helpers ──────────────────────────────────────────────────────────────────

def ok(data):
    return jsonify({"status": "ok", "data": data})

def err(msg, code=400):
    return jsonify({"status": "error", "message": str(msg)}), code

def handle(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log.exception("Request failed")
            return err(str(e), 500)
    return wrapper

def qp(name, default=None):
    return request.args.get(name, default)

def qpi(name, default=None):
    v = request.args.get(name)
    return int(v) if v is not None else default

def qpb(name, default=False):
    v = request.args.get(name, "").lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return default

# ════════════════════════════════════════════════════════════════════════════
# SEARCH
# ════════════════════════════════════════════════════════════════════════════

@app.route("/search")
@handle
def search():
    query = qp("q")
    if not query:
        return err("Missing query param: q")

    results = get_ytm().search(
        query=query,
        filter=qp("filter"),           
        limit=qpi("limit", 20),
        ignore_spelling=qpb("ignore_spelling"),
    )
    return ok(results)

@app.route("/search/suggestions")
@handle
def search_suggestions():
    query = qp("q")
    if not query:
        return err("Missing query param: q")
    results = get_ytm().get_search_suggestions(
        query=query,
        detailed_runs=qpb("detailed"),
    )
    return ok(results)

# ════════════════════════════════════════════════════════════════════════════
# BROWSING
# ════════════════════════════════════════════════════════════════════════════

@app.route("/home")
@handle
def home():
    data = get_ytm().get_home(limit=qpi("limit", 6))
    return ok(data)

@app.route("/artist/<channel_id>")
@handle
def get_artist(channel_id):
    data = get_ytm().get_artist(channel_id)
    return ok(data)

@app.route("/artist/<channel_id>/albums")
@handle
def get_artist_albums(channel_id):
    params = qp("params")
    if not params:
        return err("Missing query param: params")
    data = get_ytm().get_artist_albums(channel_id, params=params)
    return ok(data)

@app.route("/album/<browse_id>")
@handle
def get_album(browse_id):
    data = get_ytm().get_album(browse_id)
    return ok(data)

@app.route("/album/<browse_id>/browse-id")
@handle
def get_album_browse_id(browse_id):
    data = get_ytm().get_album_browse_id(browse_id)
    return ok(data)

@app.route("/user/<channel_id>")
@handle
def get_user(channel_id):
    data = get_ytm().get_user(channel_id)
    return ok(data)

@app.route("/user/<channel_id>/playlists")
@handle
def get_user_playlists(channel_id):
    params = qp("params")
    data = get_ytm().get_user_playlists(channel_id, params=params)
    return ok(data)

@app.route("/song/<video_id>")
@handle
def get_song(video_id):
    data = get_ytm().get_song(video_id)
    return ok(data)

@app.route("/song/<video_id>/related")
@handle
def get_song_related(video_id):
    data = get_ytm().get_song_related(browse_id=video_id)
    return ok(data)

@app.route("/lyrics/<browse_id>")
@handle
def get_lyrics(browse_id):
    data = get_ytm().get_lyrics(browse_id)
    return ok(data)

@app.route("/tasteprofile")
@handle
def get_tasteprofile():
    data = get_ytm().get_tasteprofile()
    return ok(data)

# ════════════════════════════════════════════════════════════════════════════
# EXPLORE (Charts / Moods)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/explore/moods")
@handle
def get_mood_categories():
    data = get_ytm().get_mood_categories()
    return ok(data)

@app.route("/explore/mood-playlists")
@handle
def get_mood_playlists():
    params = qp("params")
    if not params:
        return err("Missing query param: params")
    data = get_ytm().get_mood_playlists(params)
    return ok(data)

@app.route("/explore/charts")
@handle
def get_charts():
    country = qp("country", "ZZ")
    data = get_ytm().get_charts(country=country)
    return ok(data)

# ════════════════════════════════════════════════════════════════════════════
# WATCH / QUEUE (Next-up tracks, Radio)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/watch")
@handle
def get_watch_playlist():
    video_id   = qp("videoId")
    playlist_id = qp("playlistId")
    if not video_id and not playlist_id:
        return err("Provide at least videoId or playlistId")

    data = get_ytm().get_watch_playlist(
        videoId=video_id,
        playlistId=playlist_id,
        limit=qpi("limit", 25),
        radio=qpb("radio"),
        shuffle=qpb("shuffle"),
    )
    return ok(data)

# ════════════════════════════════════════════════════════════════════════════
# PLAYLISTS
# ════════════════════════════════════════════════════════════════════════════

@app.route("/playlist/<playlist_id>")
@handle
def get_playlist(playlist_id):
    limit = qpi("limit")   
    data = get_ytm().get_playlist(playlist_id, limit=limit)
    return ok(data)

@app.route("/playlist/<playlist_id>/suggestions")
@handle
def get_playlist_suggestions(playlist_id):
    data = get_ytm().get_playlist_suggestions(playlist_id)
    return ok(data)

@app.route("/playlist", methods=["POST"])
@handle
def create_playlist():
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).create_playlist(
        title=body["title"],
        description=body.get("description", ""),
        privacy_status=body.get("privacy_status", "PRIVATE"),
        video_ids=body.get("video_ids"),
        source_playlist=body.get("source_playlist"),
    )
    return ok(data)

@app.route("/playlist/<playlist_id>", methods=["PUT"])
@handle
def edit_playlist(playlist_id):
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).edit_playlist(
        playlistId=playlist_id,
        title=body.get("title"),
        description=body.get("description"),
        privacyStatus=body.get("privacy_status"),
    )
    return ok(data)

@app.route("/playlist/<playlist_id>", methods=["DELETE"])
@handle
def delete_playlist(playlist_id):
    data = get_ytm(needs_auth=True).delete_playlist(playlist_id)
    return ok(data)

@app.route("/playlist/<playlist_id>/tracks", methods=["POST"])
@handle
def add_playlist_items(playlist_id):
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).add_playlist_items(
        playlistId=playlist_id,
        videoIds=body.get("video_ids"),
        source_playlist=body.get("source_playlist"),
        duplicates=body.get("duplicates", False),
    )
    return ok(data)

@app.route("/playlist/<playlist_id>/tracks", methods=["DELETE"])
@handle
def remove_playlist_items(playlist_id):
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).remove_playlist_items(
        playlist_id, body["tracks"]
    )
    return ok(data)

@app.route("/playlist/<playlist_id>/tracks/move", methods=["POST"])
@handle
def move_playlist_item(playlist_id):
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).move_playlist_item(
        playlistId=playlist_id,
        setVideoId=body["set_video_id"],
        moveSetVideoIdSuccessor=body.get("move_set_video_id_successor"),
    )
    return ok(data)

# ════════════════════════════════════════════════════════════════════════════
# LIBRARY  (requires auth)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/library/playlists")
@handle
def get_library_playlists():
    data = get_ytm(needs_auth=True).get_library_playlists(limit=qpi("limit", 25))
    return ok(data)

@app.route("/library/songs")
@handle
def get_library_songs():
    data = get_ytm(needs_auth=True).get_library_songs(
        limit=qpi("limit", 25),
        order=qp("order"),
    )
    return ok(data)

@app.route("/library/albums")
@handle
def get_library_albums():
    data = get_ytm(needs_auth=True).get_library_albums(
        limit=qpi("limit", 25),
        order=qp("order"),
    )
    return ok(data)

@app.route("/library/artists")
@handle
def get_library_artists():
    data = get_ytm(needs_auth=True).get_library_artists(
        limit=qpi("limit", 25),
        order=qp("order"),
    )
    return ok(data)

@app.route("/library/subscriptions")
@handle
def get_library_subscriptions():
    data = get_ytm(needs_auth=True).get_library_subscriptions(limit=qpi("limit", 25))
    return ok(data)

@app.route("/library/podcasts")
@handle
def get_library_podcasts():
    data = get_ytm(needs_auth=True).get_library_podcasts(limit=qpi("limit", 25))
    return ok(data)

@app.route("/library/channels")
@handle
def get_library_channels():
    data = get_ytm(needs_auth=True).get_library_channels(limit=qpi("limit", 25))
    return ok(data)

@app.route("/library/history")
@handle
def get_history():
    data = get_ytm(needs_auth=True).get_history()
    return ok(data)

@app.route("/library/history", methods=["POST"])
@handle
def add_history_item():
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).add_history_item(body["song"])
    return ok(data)

@app.route("/library/history/<video_id>", methods=["DELETE"])
@handle
def remove_history_items(video_id):
    token = qp("feedbackToken")
    if not token:
        return err("Missing feedbackToken query param")
    data = get_ytm(needs_auth=True).remove_history_items([token])
    return ok(data)

# ════════════════════════════════════════════════════════════════════════════
# RATINGS / LIBRARY ACTIONS
# ════════════════════════════════════════════════════════════════════════════

@app.route("/rate/song", methods=["POST"])
@handle
def rate_song():
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).rate_song(
        body["video_id"], body["rating"]
    )
    return ok(data)

@app.route("/rate/playlist", methods=["POST"])
@handle
def rate_playlist():
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).rate_playlist(
        body["playlist_id"], body["rating"]
    )
    return ok(data)

@app.route("/subscribe", methods=["POST"])
@handle
def subscribe_artists():
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).subscribe_artists(body["channel_ids"])
    return ok(data)

@app.route("/unsubscribe", methods=["POST"])
@handle
def unsubscribe_artists():
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).unsubscribe_artists(body["channel_ids"])
    return ok(data)

# ════════════════════════════════════════════════════════════════════════════
# PODCASTS
# ════════════════════════════════════════════════════════════════════════════

@app.route("/podcast/<browse_id>")
@handle
def get_podcast(browse_id):
    data = get_ytm().get_podcast(browse_id)
    return ok(data)

@app.route("/episode/<video_id>")
@handle
def get_episode(video_id):
    data = get_ytm().get_episode(video_id)
    return ok(data)

@app.route("/channel/<channel_id>")
@handle
def get_channel(channel_id):
    data = get_ytm().get_channel(channel_id)
    return ok(data)

@app.route("/channel/<channel_id>/episodes")
@handle
def get_channel_episodes(channel_id):
    params = qp("params")
    data = get_ytm().get_channel_episodes(channel_id, params=params)
    return ok(data)

# ════════════════════════════════════════════════════════════════════════════
# UPLOADS  (requires browser auth)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/uploads/songs")
@handle
def get_library_upload_songs():
    data = get_ytm(needs_auth=True).get_library_upload_songs(
        limit=qpi("limit", 25), order=qp("order")
    )
    return ok(data)

@app.route("/uploads/artists")
@handle
def get_library_upload_artists():
    data = get_ytm(needs_auth=True).get_library_upload_artists(limit=qpi("limit", 25))
    return ok(data)

@app.route("/uploads/albums")
@handle
def get_library_upload_albums():
    data = get_ytm(needs_auth=True).get_library_upload_albums(limit=qpi("limit", 25))
    return ok(data)

@app.route("/uploads/artist/<artist_id>")
@handle
def get_library_upload_artist(artist_id):
    data = get_ytm(needs_auth=True).get_library_upload_artist(artist_id)
    return ok(data)

@app.route("/uploads/album/<album_id>")
@handle
def get_library_upload_album(album_id):
    data = get_ytm(needs_auth=True).get_library_upload_album(album_id)
    return ok(data)

@app.route("/uploads/song/<entity_id>", methods=["DELETE"])
@handle
def delete_upload_entity(entity_id):
    data = get_ytm(needs_auth=True).delete_upload_entity(entity_id)
    return ok(data)

# ════════════════════════════════════════════════════════════════════════════
# AUDIO STREAMING  —  YouTube InnerTube API (no yt-dlp, no bot detection)
# ════════════════════════════════════════════════════════════════════════════
#
# YouTube's own InnerTube API is what the official Android/iOS YouTube app
# uses internally. It is NOT the same endpoint that yt-dlp hits, so it is
# NOT subject to bot-detection challenges.
#
# Endpoint : POST https://www.youtube.com/youtubei/v1/player
# Client   : ANDROID_MUSIC  (key: AIzaSyAOghZGza2MQSZkY_zfZ370N-PUdXEo8AI)
# This gives back a direct signed CDN URL valid for ~6 hours.
# ────────────────────────────────────────────────────────────────────────────

INNERTUBE_API_KEY = "AIzaSyAOghZGza2MQSZkY_zfZ370N-PUdXEo8AI"
INNERTUBE_URL     = "https://www.youtube.com/youtubei/v1/player"

# Multiple client configs to try in order — different clients bypass different restrictions
INNERTUBE_CLIENTS = [
    {
        # iOS YouTube Music — works for most music, bypasses sign-in wall
        "name": "IOS_MUSIC",
        "key":  "AIzaSyAOghZGza2MQSZkY_zfZ370N-PUdXEo8AI",
        "context": {
            "client": {
                "clientName":    "IOS_MUSIC",
                "clientVersion": "7.08.2",
                "deviceMake":    "Apple",
                "deviceModel":   "iPhone16,2",
                "osName":        "iPhone",
                "osVersion":     "18.1.0.22B83",
                "hl": "en", "gl": "US",
            }
        },
        "user_agent": "com.google.ios.youtubemusic/7.08.2 (iPhone; CPU iPhone OS 18_1 like Mac OS X)",
        "client_name_id": "26",
    },
    {
        # Android YouTube Music — good fallback
        "name": "ANDROID_MUSIC",
        "key":  "AIzaSyAOghZGza2MQSZkY_zfZ370N-PUdXEo8AI",
        "context": {
            "client": {
                "clientName":        "ANDROID_MUSIC",
                "clientVersion":     "7.27.52",
                "androidSdkVersion": 30,
                "hl": "en", "gl": "US",
            }
        },
        "user_agent": "com.google.android.apps.youtube.music/7.27.52 (Linux; U; Android 11) gzip",
        "client_name_id": "21",
    },
    {
        # TV embedded — no sign-in check, works even for restricted videos
        "name": "TVHTML5_SIMPLY_EMBEDDED_PLAYER",
        "key":  "AIzaSyAOghZGza2MQSZkY_zfZ370N-PUdXEo8AI",
        "context": {
            "client": {
                "clientName":    "TVHTML5_SIMPLY_EMBEDDED_PLAYER",
                "clientVersion": "2.0",
                "hl": "en", "gl": "US",
            },
            "thirdParty": {
                "embedUrl": "https://www.youtube.com/"
            }
        },
        "user_agent": "Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/538.1 (KHTML, like Gecko) Version/6.0 TV Safari/538.1",
        "client_name_id": "85",
    },
    {
        # Android — broad compatibility
        "name": "ANDROID",
        "key":  "AIzaSyA8eiZmM1FaDVjRy-df2KTyQ_vz_yYM39w",
        "context": {
            "client": {
                "clientName":        "ANDROID",
                "clientVersion":     "19.29.37",
                "androidSdkVersion": 30,
                "hl": "en", "gl": "US",
            }
        },
        "user_agent": "com.google.android.youtube/19.29.37 (Linux; U; Android 11) gzip",
        "client_name_id": "3",
    },
]


def _fetch_innertube(video_id: str, client: dict) -> dict:
    """Call InnerTube /player with a specific client config."""
    payload = {
        "context":  client["context"],
        "videoId":  video_id,
        "contentCheckOk": True,
        "racyCheckOk":    True,
    }
    # TV embedded needs thirdParty in payload too
    if client["name"] == "TVHTML5_SIMPLY_EMBEDDED_PLAYER":
        payload["playbackContext"] = {
            "contentPlaybackContext": {
                "signatureTimestamp": 20000,
                "html5Preference": "HTML5_PREF_WANTS",
            }
        }

    headers = {
        "Content-Type":             "application/json",
        "User-Agent":               client["user_agent"],
        "X-YouTube-Client-Name":    client["client_name_id"],
        "X-YouTube-Client-Version": client["context"]["client"]["clientVersion"],
        "Origin":                   "https://www.youtube.com",
        "Referer":                  "https://www.youtube.com/",
    }
    resp = requests.post(
        f"{INNERTUBE_URL}?key={client['key']}",
        json=payload,
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _best_audio_format(formats: list) -> dict | None:
    """
    Pick the best audio-only format from streamingData.adaptiveFormats.
    Prefer: audio/mp4 (m4a/aac) > audio/webm (opus) > anything audio.
    Within each type, pick highest bitrate.
    """
    audio = [
        f for f in formats
        if f.get("mimeType", "").startswith("audio/")
        and f.get("url")  # must have a direct URL (not ciphered)
    ]
    if not audio:
        return None

    def score(f):
        mime    = f.get("mimeType", "")
        bitrate = f.get("averageBitrate", f.get("bitrate", 0))
        type_score = 2 if "mp4" in mime else (1 if "webm" in mime else 0)
        return (type_score, bitrate)

    return max(audio, key=score)


@app.route("/stream/<video_id>")
@handle
def get_stream_url(video_id):
    """
    GET /stream/<videoId>
    Tries multiple InnerTube clients until one returns a playable URL.
    """
    last_error = "No clients attempted"

    for client in INNERTUBE_CLIENTS:
        try:
            player  = _fetch_innertube(video_id, client)
            status  = player.get("playabilityStatus", {})
            ps      = status.get("status", "UNKNOWN")

            if ps not in ("OK", "LIVE_STREAM_OFFLINE"):
                reason = status.get("reason", ps)
                log.warning(f"[{client['name']}] {video_id} not playable: {reason}")
                last_error = reason
                continue

            streaming = player.get("streamingData", {})
            formats   = (streaming.get("adaptiveFormats", []) +
                         streaming.get("formats", []))

            best = _best_audio_format(formats)
            if not best:
                # Try any format with a URL as last resort
                candidates = [f for f in formats if f.get("url")]
                if candidates:
                    best = max(candidates, key=lambda f: f.get("bitrate", 0))

            if best and best.get("url"):
                mime    = best.get("mimeType", "audio/mp4")
                ext     = "m4a" if "mp4" in mime else "webm"
                bitrate = best.get("averageBitrate", best.get("bitrate", 0))
                log.info(f"✅ [{client['name']}] {video_id} [{ext} {bitrate//1000}kbps]")
                return ok({
                    "url":     best["url"],
                    "ext":     ext,
                    "mime":    mime,
                    "bitrate": bitrate,
                    "videoId": video_id,
                    "source":  client["name"],
                })

            log.warning(f"[{client['name']}] no direct URL in formats for {video_id}")
            last_error = "No direct URL in streamingData"

        except Exception as e:
            log.warning(f"[{client['name']}] failed for {video_id}: {e}")
            last_error = str(e)

    log.error(f"❌ All clients failed for {video_id}. Last error: {last_error}")
    return err(f"Could not resolve stream for {video_id}: {last_error}", 503)


@app.route("/stream/debug")
@handle
def stream_debug():
    """GET /stream/debug — test all InnerTube clients on a real music track."""
    test_id = "OtWjS4I2ojU"  # The exact video that was failing
    results = {}

    for client in INNERTUBE_CLIENTS:
        try:
            player  = _fetch_innertube(test_id, client)
            ps      = player.get("playabilityStatus", {}).get("status", "?")
            formats = (
                player.get("streamingData", {}).get("adaptiveFormats", []) +
                player.get("streamingData", {}).get("formats", [])
            )
            best = _best_audio_format(formats)
            if best and best.get("url"):
                mime = best.get("mimeType","")
                br   = best.get("averageBitrate", best.get("bitrate",0))
                results[client["name"]] = (
                    f"✅ WORKS — {mime[:30]} {br//1000}kbps"
                )
            else:
                results[client["name"]] = f"❌ playability={ps}, no direct URL"
        except Exception as e:
            results[client["name"]] = f"❌ {str(e)[:120]}"

    working = [k for k,v in results.items() if v.startswith("✅")]
    return ok({
        "test_video": test_id,
        "results":    results,
        "working":    working,
        "recommended": working[0] if working else "NONE",
    })

@app.route("/status")
def status():
    auth_active = os.path.exists(AUTH_FILE)
    return jsonify({
        "status": "ok",
        "server": "Exyplay Music Server",
        "version": "1.0.0",
        "ytmusicapi": "1.11.6",
        "auth_enabled": auth_active,
        "auth_file": AUTH_FILE if auth_active else None,
    })

# ════════════════════════════════════════════════════════════════════════════
# Entry point
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    log.info(f"🎵 Exyplay Music Server starting on port {port}")
    log.info(f"   Auth: {'✅ ' + AUTH_FILE if os.path.exists(AUTH_FILE) else '⚠️  No auth — public endpoints only'}")
    app.run(host="0.0.0.0", port=port, debug=debug)
