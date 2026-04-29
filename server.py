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

# ── ytmusicapi ──────────────────────────────────────────────────────────────
from ytmusicapi import YTMusic

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("exyplay")

# ── Auth setup ───────────────────────────────────────────────────────────────
# The server supports two modes:
#   1. Unauthenticated — search, browse, public playlists (no credentials needed)
#   2. Browser auth   — full library access using browser.json
#
# Place browser.json (generated via `ytmusicapi browser`) in the same directory.
# If missing, the server falls back to unauthenticated mode automatically.

AUTH_FILE = os.getenv("YTMUSIC_AUTH_FILE", "browser.json")

def _get_ytmusic(auth=True):
    """Return a YTMusic instance. Falls back to unauth if file missing."""
    if auth and os.path.exists(AUTH_FILE):
        return YTMusic(AUTH_FILE, language="en")
    return YTMusic(language="en")

# Reuse a single unauth instance for public endpoints (faster)
_ytm_public = _get_ytmusic(auth=False)
_ytm_auth   = None   # lazily created when auth file present


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
    """Decorator: catch exceptions and return JSON error."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log.exception("Request failed")
            return err(str(e), 500)
    return wrapper

def qp(name, default=None):
    """Get query param."""
    return request.args.get(name, default)

def qpi(name, default=None):
    """Get integer query param."""
    v = request.args.get(name)
    return int(v) if v is not None else default

def qpb(name, default=False):
    """Get boolean query param."""
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
    """
    GET /search?q=Oasis+Wonderwall
    Optional: filter=songs|videos|albums|artists|playlists
              limit=20
              ignore_spelling=false
    """
    query = qp("q")
    if not query:
        return err("Missing query param: q")

    results = get_ytm().search(
        query=query,
        filter=qp("filter"),           # None → all types
        limit=qpi("limit", 20),
        ignore_spelling=qpb("ignore_spelling"),
    )
    return ok(results)


@app.route("/search/suggestions")
@handle
def search_suggestions():
    """
    GET /search/suggestions?q=fad
    Optional: detailed=false
    """
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
    """
    GET /home?limit=6
    Returns personalised home rows (needs auth for personalised content).
    """
    data = get_ytm().get_home(limit=qpi("limit", 6))
    return ok(data)


@app.route("/artist/<channel_id>")
@handle
def get_artist(channel_id):
    """GET /artist/<channelId>"""
    data = get_ytm().get_artist(channel_id)
    return ok(data)


@app.route("/artist/<channel_id>/albums")
@handle
def get_artist_albums(channel_id):
    """
    GET /artist/<channelId>/albums?params=<params>
    params comes from get_artist() albums.params
    """
    params = qp("params")
    if not params:
        return err("Missing query param: params")
    data = get_ytm().get_artist_albums(channel_id, params=params)
    return ok(data)


@app.route("/album/<browse_id>")
@handle
def get_album(browse_id):
    """GET /album/<browseId>"""
    data = get_ytm().get_album(browse_id)
    return ok(data)


@app.route("/album/<browse_id>/browse-id")
@handle
def get_album_browse_id(browse_id):
    """GET /album/<audioPlaylistId>/browse-id — converts playlist ID to browseId"""
    data = get_ytm().get_album_browse_id(browse_id)
    return ok(data)


@app.route("/user/<channel_id>")
@handle
def get_user(channel_id):
    """GET /user/<channelId>"""
    data = get_ytm().get_user(channel_id)
    return ok(data)


@app.route("/user/<channel_id>/playlists")
@handle
def get_user_playlists(channel_id):
    """GET /user/<channelId>/playlists?params=<params>"""
    params = qp("params")
    data = get_ytm().get_user_playlists(channel_id, params=params)
    return ok(data)


@app.route("/song/<video_id>")
@handle
def get_song(video_id):
    """
    GET /song/<videoId>
    Returns metadata for a single song/video.
    """
    data = get_ytm().get_song(video_id)
    return ok(data)


@app.route("/song/<video_id>/related")
@handle
def get_song_related(video_id):
    """GET /song/<videoId>/related"""
    data = get_ytm().get_song_related(browse_id=video_id)
    return ok(data)


@app.route("/lyrics/<browse_id>")
@handle
def get_lyrics(browse_id):
    """
    GET /lyrics/<browseId>
    browseId comes from get_watch_playlist() trackList[n].lyrics
    """
    data = get_ytm().get_lyrics(browse_id)
    return ok(data)


@app.route("/tasteprofile")
@handle
def get_tasteprofile():
    """GET /tasteprofile — returns taste profile artists"""
    data = get_ytm().get_tasteprofile()
    return ok(data)


# ════════════════════════════════════════════════════════════════════════════
# EXPLORE (Charts / Moods)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/explore/moods")
@handle
def get_mood_categories():
    """GET /explore/moods"""
    data = get_ytm().get_mood_categories()
    return ok(data)


@app.route("/explore/mood-playlists")
@handle
def get_mood_playlists():
    """
    GET /explore/mood-playlists?params=<params>
    params from get_mood_categories()
    """
    params = qp("params")
    if not params:
        return err("Missing query param: params")
    data = get_ytm().get_mood_playlists(params)
    return ok(data)


@app.route("/explore/charts")
@handle
def get_charts():
    """
    GET /explore/charts
    Optional: country=ZZ  (ZZ = global)
    """
    country = qp("country", "ZZ")
    data = get_ytm().get_charts(country=country)
    return ok(data)


# ════════════════════════════════════════════════════════════════════════════
# WATCH / QUEUE (Next-up tracks, Radio)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/watch")
@handle
def get_watch_playlist():
    """
    GET /watch?videoId=<id>
    Optional: playlistId=<id>  limit=25  radio=false  shuffle=false
    Returns upcoming tracks + lyrics browseId.
    """
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
    """
    GET /playlist/<playlistId>
    Optional: limit=100  (None = all tracks)
    """
    limit = qpi("limit")   # None means return everything
    data = get_ytm().get_playlist(playlist_id, limit=limit)
    return ok(data)


@app.route("/playlist/<playlist_id>/suggestions")
@handle
def get_playlist_suggestions(playlist_id):
    """GET /playlist/<playlistId>/suggestions"""
    data = get_ytm().get_playlist_suggestions(playlist_id)
    return ok(data)


# ── Authenticated playlist mutations ─────────────────────────────────────────

@app.route("/playlist", methods=["POST"])
@handle
def create_playlist():
    """
    POST /playlist
    Body: { title, description?, privacy_status?, video_ids?, source_playlist? }
    privacy_status: PUBLIC | PRIVATE | UNLISTED
    """
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
    """
    PUT /playlist/<playlistId>
    Body: { title?, description?, privacy_status? }
    """
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
    """DELETE /playlist/<playlistId>"""
    data = get_ytm(needs_auth=True).delete_playlist(playlist_id)
    return ok(data)


@app.route("/playlist/<playlist_id>/tracks", methods=["POST"])
@handle
def add_playlist_items(playlist_id):
    """
    POST /playlist/<playlistId>/tracks
    Body: { video_ids: [...], source_playlist?: "PLxxx", duplicates?: false }
    """
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
    """
    DELETE /playlist/<playlistId>/tracks
    Body: { tracks: [{ videoId, setVideoId }] }
    setVideoId comes from get_playlist() tracks[n].setVideoId
    """
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).remove_playlist_items(
        playlist_id, body["tracks"]
    )
    return ok(data)


@app.route("/playlist/<playlist_id>/tracks/move", methods=["POST"])
@handle
def move_playlist_item(playlist_id):
    """
    POST /playlist/<playlistId>/tracks/move
    Body: { set_video_id, move_set_video_id_successor? }
    """
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
    """GET /library/playlists?limit=25"""
    data = get_ytm(needs_auth=True).get_library_playlists(limit=qpi("limit", 25))
    return ok(data)


@app.route("/library/songs")
@handle
def get_library_songs():
    """GET /library/songs?limit=25&order=a_to_z|z_to_a|recently_added"""
    data = get_ytm(needs_auth=True).get_library_songs(
        limit=qpi("limit", 25),
        order=qp("order"),
    )
    return ok(data)


@app.route("/library/albums")
@handle
def get_library_albums():
    """GET /library/albums?limit=25&order=..."""
    data = get_ytm(needs_auth=True).get_library_albums(
        limit=qpi("limit", 25),
        order=qp("order"),
    )
    return ok(data)


@app.route("/library/artists")
@handle
def get_library_artists():
    """GET /library/artists?limit=25&order=..."""
    data = get_ytm(needs_auth=True).get_library_artists(
        limit=qpi("limit", 25),
        order=qp("order"),
    )
    return ok(data)


@app.route("/library/subscriptions")
@handle
def get_library_subscriptions():
    """GET /library/subscriptions?limit=25"""
    data = get_ytm(needs_auth=True).get_library_subscriptions(limit=qpi("limit", 25))
    return ok(data)


@app.route("/library/podcasts")
@handle
def get_library_podcasts():
    """GET /library/podcasts?limit=25"""
    data = get_ytm(needs_auth=True).get_library_podcasts(limit=qpi("limit", 25))
    return ok(data)


@app.route("/library/channels")
@handle
def get_library_channels():
    """GET /library/channels?limit=25"""
    data = get_ytm(needs_auth=True).get_library_channels(limit=qpi("limit", 25))
    return ok(data)


@app.route("/library/history")
@handle
def get_history():
    """GET /library/history — recently played tracks"""
    data = get_ytm(needs_auth=True).get_history()
    return ok(data)


@app.route("/library/history", methods=["POST"])
@handle
def add_history_item():
    """
    POST /library/history
    Body: { song: <song object from get_song()> }
    """
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).add_history_item(body["song"])
    return ok(data)


@app.route("/library/history/<video_id>", methods=["DELETE"])
@handle
def remove_history_items(video_id):
    """DELETE /library/history/<videoId>"""
    # The API takes a list of feedbackTokens from get_history()
    # Client must pass feedbackToken as query param
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
    """
    POST /rate/song
    Body: { video_id, rating }  rating: LIKE | DISLIKE | INDIFFERENT
    """
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).rate_song(
        body["video_id"], body["rating"]
    )
    return ok(data)


@app.route("/rate/playlist", methods=["POST"])
@handle
def rate_playlist():
    """
    POST /rate/playlist
    Body: { playlist_id, rating }  rating: LIKE | INDIFFERENT
    """
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).rate_playlist(
        body["playlist_id"], body["rating"]
    )
    return ok(data)


@app.route("/subscribe", methods=["POST"])
@handle
def subscribe_artists():
    """
    POST /subscribe
    Body: { channel_ids: [...] }
    """
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).subscribe_artists(body["channel_ids"])
    return ok(data)


@app.route("/unsubscribe", methods=["POST"])
@handle
def unsubscribe_artists():
    """
    POST /unsubscribe
    Body: { channel_ids: [...] }
    """
    body = request.get_json(force=True)
    data = get_ytm(needs_auth=True).unsubscribe_artists(body["channel_ids"])
    return ok(data)


# ════════════════════════════════════════════════════════════════════════════
# PODCASTS
# ════════════════════════════════════════════════════════════════════════════

@app.route("/podcast/<browse_id>")
@handle
def get_podcast(browse_id):
    """GET /podcast/<browseId>"""
    data = get_ytm().get_podcast(browse_id)
    return ok(data)


@app.route("/episode/<video_id>")
@handle
def get_episode(video_id):
    """GET /episode/<videoId>"""
    data = get_ytm().get_episode(video_id)
    return ok(data)


@app.route("/channel/<channel_id>")
@handle
def get_channel(channel_id):
    """GET /channel/<channelId>"""
    data = get_ytm().get_channel(channel_id)
    return ok(data)


@app.route("/channel/<channel_id>/episodes")
@handle
def get_channel_episodes(channel_id):
    """GET /channel/<channelId>/episodes?params=<params>"""
    params = qp("params")
    data = get_ytm().get_channel_episodes(channel_id, params=params)
    return ok(data)


# ════════════════════════════════════════════════════════════════════════════
# UPLOADS  (requires browser auth)
# ════════════════════════════════════════════════════════════════════════════

@app.route("/uploads/songs")
@handle
def get_library_upload_songs():
    """GET /uploads/songs?limit=25&order=..."""
    data = get_ytm(needs_auth=True).get_library_upload_songs(
        limit=qpi("limit", 25), order=qp("order")
    )
    return ok(data)


@app.route("/uploads/artists")
@handle
def get_library_upload_artists():
    """GET /uploads/artists?limit=25"""
    data = get_ytm(needs_auth=True).get_library_upload_artists(limit=qpi("limit", 25))
    return ok(data)


@app.route("/uploads/albums")
@handle
def get_library_upload_albums():
    """GET /uploads/albums?limit=25"""
    data = get_ytm(needs_auth=True).get_library_upload_albums(limit=qpi("limit", 25))
    return ok(data)


@app.route("/uploads/artist/<artist_id>")
@handle
def get_library_upload_artist(artist_id):
    """GET /uploads/artist/<artistId>"""
    data = get_ytm(needs_auth=True).get_library_upload_artist(artist_id)
    return ok(data)


@app.route("/uploads/album/<album_id>")
@handle
def get_library_upload_album(album_id):
    """GET /uploads/album/<albumId>"""
    data = get_ytm(needs_auth=True).get_library_upload_album(album_id)
    return ok(data)


@app.route("/uploads/song/<entity_id>", methods=["DELETE"])
@handle
def delete_upload_entity(entity_id):
    """DELETE /uploads/song/<entityId>"""
    data = get_ytm(needs_auth=True).delete_upload_entity(entity_id)
    return ok(data)


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
