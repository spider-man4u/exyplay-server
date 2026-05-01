"""
Exyplay Music Server
Flask REST API wrapping ytmusicapi for the Exyplay Android app.
Run: python server.py
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import logging
from functools import wraps
import requests
import yt_dlp

# ── ytmusicapi ──────────────────────────────────────────────────────────────
from ytmusicapi import YTMusic

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("exyplay")

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
# AUDIO STREAMING (Multi-Node Anti-Bot Router)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/stream/<video_id>")
@handle
def get_stream_url(video_id):
    """
    GET /stream/<videoId>
    Tries cookies+android, cookies+tv_embedded, bare android,
    bare tv_embedded, then Piped — in that order.
    """
    COOKIES_FILE = os.getenv("COOKIES_FILE", "/etc/secrets/cookies.txt")
    yt_url       = f"https://www.youtube.com/watch?v={video_id}"
    cookies_ok   = os.path.exists(COOKIES_FILE)

    log.info(f"▶ /stream/{video_id}  cookies_file={COOKIES_FILE}  exists={cookies_ok}")

    def try_ytdlp(client, use_cookies):
        opts = {
            "format":        "bestaudio/best",
            "quiet":         True,
            "no_warnings":   True,
            "skip_download": True,
            "extractor_args": {
                "youtube": {"player_client": [client]}
            },
        }
        if use_cookies and cookies_ok:
            opts["cookiefile"] = COOKIES_FILE
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(yt_url, download=False)
        return info.get("url", ""), info.get("ext", "webm")

    # Attempt order
    attempts = [
        ("android",    True),
        ("tv_embedded", True),
        ("android",    False),
        ("tv_embedded", False),
    ]

    for client, use_cookies in attempts:
        label = f"{'cookies+' if use_cookies else ''}{client}"
        try:
            url, ext = try_ytdlp(client, use_cookies)
            if url:
                log.info(f"✅ {label} → {video_id} [{ext}]")
                return ok({"url": url, "ext": ext,
                           "videoId": video_id, "source": label})
            log.warning(f"⚠️  {label} returned empty URL")
        except Exception as e:
            log.warning(f"❌ {label} failed: {e}")

    # Piped fallback
    for base in ["https://pipedapi.kavin.rocks",
                 "https://pipedapi.tokhmi.xyz",
                 "https://pipedapi.smnz.de",
                 "https://piped-api.garudalinux.org"]:
        try:
            res     = requests.get(f"{base}/streams/{video_id}",
                                   timeout=6,
                                   headers={"User-Agent": "Exyplay/1.0"}).json()
            streams = res.get("audioStreams", [])
            if not streams:
                continue
            chosen, ext = None, "webm"
            for s in streams:
                if "mp4" in s.get("mimeType","") or "m4a" in s.get("mimeType",""):
                    chosen, ext = s.get("url"), "m4a"
                    break
            if not chosen:
                chosen = streams[0].get("url","")
            if chosen:
                log.info(f"✅ Piped {base} → {video_id}")
                return ok({"url": chosen, "ext": ext,
                           "videoId": video_id, "source": "piped"})
        except Exception as e:
            log.warning(f"Piped {base} failed: {e}")

    log.error(f"❌ All strategies exhausted for {video_id}")
    return err(
        f"Could not resolve stream for {video_id}. "
        "Check Render logs for details — run /stream/debug to diagnose.",
        503
    )


@app.route("/stream/findcookies")
@handle
def find_cookies():
    """GET /stream/findcookies — scan filesystem to locate cookies.txt on Render."""
    search_paths = [
        "/etc/secrets/cookies.txt",
        "/etc/secrets/cookies",
        "/opt/render/project/src/cookies.txt",
        "/opt/render/project/cookies.txt",
        "cookies.txt",
        os.path.join(os.getcwd(), "cookies.txt"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt"),
    ]
    found = {}
    for p in search_paths:
        found[p] = "✅ EXISTS" if os.path.exists(p) else "❌ not found"

    secrets_dir = {}
    if os.path.isdir("/etc/secrets"):
        try:
            secrets_dir = {
                f: f"{os.path.getsize(os.path.join('/etc/secrets', f))} bytes"
                for f in os.listdir("/etc/secrets")
            }
        except Exception as e:
            secrets_dir = {"error": str(e)}
    else:
        secrets_dir = {"note": "/etc/secrets directory does not exist"}

    return ok({
        "cwd": os.getcwd(),
        "script_dir": os.path.dirname(os.path.abspath(__file__)),
        "search_results": found,
        "etc_secrets_contents": secrets_dir,
        "env_COOKIES_FILE": os.getenv("COOKIES_FILE", "NOT SET"),
    })


@app.route("/stream/debug")
@handle
def stream_debug():
    """GET /stream/debug — diagnose which extraction methods work on this IP."""
    test_id = "dQw4w9WgXcQ"
    results = {}
    COOKIES_FILE = os.getenv("COOKIES_FILE", "/etc/secrets/cookies.txt")

    # Test cookies
    if os.path.exists(COOKIES_FILE):
        try:
            ydl_opts = {
                "format": "bestaudio/best", "quiet": True,
                "no_warnings": True, "skip_download": True,
                "cookiefile": COOKIES_FILE,
                "extractor_args": {"youtube": {"player_client": ["web"]}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={test_id}", download=False)
            results["cookies+web"] = "✅ WORKS" if info.get("url") else "❌ empty"
        except Exception as e:
            results["cookies+web"] = f"❌ {str(e)[:100]}"
    else:
        results["cookies+web"] = f"⚠️  No cookies.txt at '{COOKIES_FILE}'"

    # Test each client without cookies
    for client in ["tv_embedded", "ios", "android", "mweb", "web"]:
        try:
            ydl_opts = {
                "format": "bestaudio/best", "quiet": True,
                "no_warnings": True, "skip_download": True,
                "extractor_args": {
                    "youtube": {
                        "player_client": [client],
                        "player_skip": ["webpage", "configs"],
                    }
                },
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={test_id}", download=False)
            results[client] = "✅ WORKS" if info.get("url") else "❌ empty"
        except Exception as e:
            msg = str(e)
            if "Sign in" in msg or "bot" in msg:
                results[client] = "🔴 BOT BLOCKED"
            elif "429" in msg:
                results[client] = "🟡 RATE LIMITED"
            else:
                results[client] = f"❌ {msg[:100]}"

    # Test Piped
    try:
        res = requests.get(
            f"https://pipedapi.kavin.rocks/streams/{test_id}", timeout=5).json()
        results["piped"] = "✅ WORKS" if res.get("audioStreams") else f"❌ {res.get('error')}"
    except Exception as e:
        results["piped"] = f"❌ {str(e)[:80]}"

    working = [k for k, v in results.items() if v.startswith("✅")]
    return ok({
        "test_video": test_id,
        "cookies_file": COOKIES_FILE,
        "cookies_present": os.path.exists(COOKIES_FILE),
        "results": results,
        "working_methods": working,
        "recommendation": working[0] if working else "NONE — add cookies.txt",
    })

# ════════════════════════════════════════════════════════════════════════════
# STATUS
# ════════════════════════════════════════════════════════════════════════════

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
