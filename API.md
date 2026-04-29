# Exyplay Music Server — API Reference

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Authentication (optional but recommended)

**Browser auth** (full library access):
```bash
ytmusicapi browser
# Follow prompts, creates browser.json
```
Place `browser.json` in the same folder as `server.py`.

Without `browser.json`, only public endpoints work (search, browse, playlists, watch).

### 3. Run the server
```bash
python server.py
# Or with custom port/auth file:
PORT=8080 YTMUSIC_AUTH_FILE=browser.json python server.py
```

---

## All Endpoints

### Status
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | Server health + auth status |

---

### 🔍 Search
| Method | Endpoint | Params | Auth |
|--------|----------|--------|------|
| GET | `/search` | `q`, `filter`, `limit`, `ignore_spelling` | No |
| GET | `/search/suggestions` | `q`, `detailed` | No |

**filter values:** `songs` · `videos` · `albums` · `artists` · `playlists` · `community_playlists` · `featured_playlists` · `uploads`

**Examples:**
```
GET /search?q=Blinding+Lights
GET /search?q=The+Weeknd&filter=songs&limit=10
GET /search/suggestions?q=blind
```

---

### 🏠 Browse
| Method | Endpoint | Params | Auth |
|--------|----------|--------|------|
| GET | `/home` | `limit` | Recommended |
| GET | `/artist/<channelId>` | — | No |
| GET | `/artist/<channelId>/albums` | `params` | No |
| GET | `/album/<browseId>` | — | No |
| GET | `/user/<channelId>` | — | No |
| GET | `/user/<channelId>/playlists` | `params` | No |
| GET | `/song/<videoId>` | — | No |
| GET | `/song/<videoId>/related` | — | No |
| GET | `/lyrics/<browseId>` | — | No |
| GET | `/tasteprofile` | — | No |

**Notes:**
- `artist.albums.browseId` + `artist.albums.params` → pass to `/artist/{id}/albums?params=...`
- `watch` tracklist returns `lyrics` browseId → pass to `/lyrics/<browseId>`

---

### 🎶 Watch / Queue
| Method | Endpoint | Params | Auth |
|--------|----------|--------|------|
| GET | `/watch` | `videoId`, `playlistId`, `limit`, `radio`, `shuffle` | No |

**Example (radio from a song):**
```
GET /watch?videoId=ZrOKjDZOtkA&radio=true&limit=50
```
Returns `tracks[]` (each with `videoId`, `title`, `artists`, `thumbnails`, `lyrics`) + `lyrics` browseId.

---

### 🎵 Playlists
| Method | Endpoint | Body / Params | Auth |
|--------|----------|---------------|------|
| GET | `/playlist/<playlistId>` | `limit` | No |
| GET | `/playlist/<playlistId>/suggestions` | — | No |
| POST | `/playlist` | `{title, description?, privacy_status?, video_ids?, source_playlist?}` | **Yes** |
| PUT | `/playlist/<playlistId>` | `{title?, description?, privacy_status?}` | **Yes** |
| DELETE | `/playlist/<playlistId>` | — | **Yes** |
| POST | `/playlist/<playlistId>/tracks` | `{video_ids?, source_playlist?, duplicates?}` | **Yes** |
| DELETE | `/playlist/<playlistId>/tracks` | `{tracks: [{videoId, setVideoId}]}` | **Yes** |
| POST | `/playlist/<playlistId>/tracks/move` | `{set_video_id, move_set_video_id_successor?}` | **Yes** |

`privacy_status`: `PUBLIC` · `PRIVATE` · `UNLISTED`

---

### 📚 Library (auth required)
| Method | Endpoint | Params |
|--------|----------|--------|
| GET | `/library/playlists` | `limit` |
| GET | `/library/songs` | `limit`, `order` |
| GET | `/library/albums` | `limit`, `order` |
| GET | `/library/artists` | `limit`, `order` |
| GET | `/library/subscriptions` | `limit` |
| GET | `/library/podcasts` | `limit` |
| GET | `/library/channels` | `limit` |
| GET | `/library/history` | — |
| POST | `/library/history` | `{song: <song object>}` |
| DELETE | `/library/history/<videoId>` | `feedbackToken` (query param) |

**order values:** `a_to_z` · `z_to_a` · `recently_added`

---

### ❤️ Ratings & Subscriptions (auth required)
| Method | Endpoint | Body |
|--------|----------|------|
| POST | `/rate/song` | `{video_id, rating}` — `LIKE`/`DISLIKE`/`INDIFFERENT` |
| POST | `/rate/playlist` | `{playlist_id, rating}` — `LIKE`/`INDIFFERENT` |
| POST | `/subscribe` | `{channel_ids: [...]}` |
| POST | `/unsubscribe` | `{channel_ids: [...]}` |

---

### 🌍 Explore
| Method | Endpoint | Params | Auth |
|--------|----------|--------|------|
| GET | `/explore/moods` | — | No |
| GET | `/explore/mood-playlists` | `params` | No |
| GET | `/explore/charts` | `country` (default: ZZ = global) | No |

**Example:**
```
GET /explore/charts?country=IN
GET /explore/charts        (global)
```

---

### 🎙 Podcasts
| Method | Endpoint | Params | Auth |
|--------|----------|--------|------|
| GET | `/podcast/<browseId>` | — | No |
| GET | `/episode/<videoId>` | — | No |
| GET | `/channel/<channelId>` | — | No |
| GET | `/channel/<channelId>/episodes` | `params` | No |

---

### ☁️ Uploads (auth required)
| Method | Endpoint | Params |
|--------|----------|--------|
| GET | `/uploads/songs` | `limit`, `order` |
| GET | `/uploads/artists` | `limit` |
| GET | `/uploads/albums` | `limit` |
| GET | `/uploads/artist/<artistId>` | — |
| GET | `/uploads/album/<albumId>` | — |
| DELETE | `/uploads/song/<entityId>` | — |

---

## Response Format

All endpoints return:
```json
{ "status": "ok", "data": <payload> }
```

Errors:
```json
{ "status": "error", "message": "reason" }
```

---

## Android Integration (Exyplay)

Use **Retrofit** or **OkHttp** to call this server. Example base URL:
```
http://10.0.2.2:5000   ← emulator (maps to your PC's localhost)
http://192.168.x.x:5000 ← real device on same Wi-Fi
```

### Recommended flow for playback:
1. `/search?q=...&filter=songs` → get `videoId`
2. `/watch?videoId=<id>&radio=true` → get queue + `lyrics` browseId
3. Use `videoId` with **yt-dlp** or **NewPipe Extractor** to get the actual stream URL
4. `/lyrics/<browseId>` → show lyrics while playing

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Server port |
| `YTMUSIC_AUTH_FILE` | `browser.json` | Path to auth credentials |
| `DEBUG` | `false` | Flask debug mode |
