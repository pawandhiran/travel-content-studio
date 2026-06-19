"""Trending music and Instagram trends service.

Combines Spotify trending music, local music library scanning, and
Instagram trend fetching (via RapidAPI) into a unified service for
content creation workflows.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import get_settings
from core.errors import ExternalServiceError, ProcessingError
from core.logging_config import get_logger

log = get_logger(__name__)

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

try:
    import requests

    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class TrendingSong:
    """A trending song with metadata."""

    title: str
    artist: str
    bpm: Optional[float] = None
    genre: Optional[str] = None
    source: str = "local"
    preview_url: Optional[str] = None
    spotify_id: Optional[str] = None
    duration_ms: Optional[int] = None
    local_path: Optional[str] = None
    rank: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrendingAudio:
    """A trending Instagram audio/sound."""

    audio_id: str
    name: str
    artist: str
    use_count: int
    is_original: bool
    duration_seconds: float
    preview_url: Optional[str] = None
    trending_rank: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Spotify client
# ---------------------------------------------------------------------------


class _SpotifyClient:
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE = "https://api.spotify.com/v1"

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    def _get_token(self) -> str:
        if self._access_token and self._token_expiry and datetime.now() < self._token_expiry:
            return self._access_token

        if not _REQUESTS_AVAILABLE and not _HTTPX_AVAILABLE:
            raise ExternalServiceError("No HTTP library available (install httpx or requests)")

        if _REQUESTS_AVAILABLE:
            import requests as req

            resp = req.post(
                self.TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self._client_id, self._client_secret),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        else:
            import httpx

            resp = httpx.post(
                self.TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self._client_id, self._client_secret),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

        self._access_token = data["access_token"]
        self._token_expiry = datetime.now() + timedelta(seconds=data["expires_in"] - 60)
        return self._access_token

    def _api_get(self, endpoint: str, params: dict | None = None) -> dict:
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        if _REQUESTS_AVAILABLE:
            import requests as req

            resp = req.get(
                f"{self.API_BASE}/{endpoint}",
                headers=headers,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        else:
            import httpx

            resp = httpx.get(
                f"{self.API_BASE}/{endpoint}",
                headers=headers,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    def get_viral_tracks(self, limit: int = 20) -> list[TrendingSong]:
        viral_playlists = [
            "37i9dQZEVXbLiRSasKsNU9",
            "37i9dQZEVXbMDoHDwVN2tF",
            "37i9dQZF1DXcBWIGoYBM5M",
        ]

        songs: list[TrendingSong] = []
        seen_ids: set[str] = set()

        for playlist_id in viral_playlists:
            try:
                data = self._api_get(f"playlists/{playlist_id}/tracks", {"limit": limit})
                for item in data.get("items", []):
                    track = item.get("track")
                    if not track or track["id"] in seen_ids:
                        continue
                    seen_ids.add(track["id"])

                    songs.append(
                        TrendingSong(
                            title=track["name"],
                            artist=", ".join(a["name"] for a in track["artists"]),
                            source="spotify",
                            preview_url=track.get("preview_url"),
                            spotify_id=track["id"],
                            duration_ms=track.get("duration_ms"),
                            rank=len(songs) + 1,
                        )
                    )
                    if len(songs) >= limit:
                        break
            except Exception as exc:
                log.warning("trending.spotify_playlist_error", playlist=playlist_id, error=str(exc))
                continue

            if len(songs) >= limit:
                break

        return songs

    def enrich_bpm(self, songs: list[TrendingSong]) -> list[TrendingSong]:
        for song in songs:
            if song.spotify_id:
                try:
                    features = self._api_get(f"audio-features/{song.spotify_id}")
                    song.bpm = features.get("tempo")
                except Exception:
                    pass
        return songs


# ---------------------------------------------------------------------------
# Instagram trends via RapidAPI
# ---------------------------------------------------------------------------


def _rapidapi_get(endpoint: str, params: dict | None = None) -> dict:
    api_key = os.environ.get("RAPIDAPI_KEY", "")
    if not api_key:
        return {}

    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "instagram-scraper-api2.p.rapidapi.com",
    }
    url = f"https://instagram-scraper-api2.p.rapidapi.com/v1/{endpoint}"

    if _REQUESTS_AVAILABLE:
        import requests as req

        resp = req.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            return {}
        return resp.json()
    elif _HTTPX_AVAILABLE:
        import httpx

        resp = httpx.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            return {}
        return resp.json()
    return {}


# ---------------------------------------------------------------------------
# Curated demo data (when APIs are not configured)
# ---------------------------------------------------------------------------

_DEMO_SONGS: list[dict] = [
    {"title": "Golden Hour", "artist": "JVKE", "bpm": 110, "genre": "pop"},
    {"title": "Sunset Lover", "artist": "Petit Biscuit", "bpm": 100, "genre": "chill"},
    {"title": "Paradise", "artist": "Ikson", "bpm": 120, "genre": "travel"},
    {"title": "On My Way", "artist": "Axel Johansson", "bpm": 128, "genre": "edm"},
    {"title": "Adventure", "artist": "JJD", "bpm": 130, "genre": "ncs"},
    {"title": "Vlog No Copyright", "artist": "Joakim Karud", "bpm": 95, "genre": "acoustic"},
    {"title": "Feel Good", "artist": "Syn Cole", "bpm": 125, "genre": "house"},
    {"title": "Tropical Vibes", "artist": "Ehrling", "bpm": 115, "genre": "tropical"},
    {"title": "Summer Breeze", "artist": "LAKEY INSPIRED", "bpm": 90, "genre": "lofi"},
    {"title": "Lost Sky - Dreams", "artist": "Lost Sky", "bpm": 140, "genre": "ncs"},
]

_DEMO_TRENDS: dict = {
    "trending_reels": [
        {"caption": "Travel hack you NEED to know", "views": 2_500_000, "audio": "Golden Hour - JVKE"},
        {"caption": "POV: your first time in Bali", "views": 1_800_000, "audio": "Sunset Lover"},
        {"caption": "3 places you MUST visit", "views": 3_100_000, "audio": "original audio"},
    ],
    "trending_audio": [
        {"name": "Golden Hour", "artist": "JVKE", "use_count": 850_000},
        {"name": "original sound - travel", "artist": "various", "use_count": 620_000},
        {"name": "Aesthetic vibes", "artist": "trending", "use_count": 410_000},
    ],
    "content_tips": [
        "Hook viewers in first 0.5s with motion or text",
        "Use trending audio for 2-3x reach boost",
        "Post between 7-9 PM local time for best engagement",
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_trending_music(
    sources: list[str] | None = None,
    limit: int = 20,
) -> list[TrendingSong]:
    """
    Fetch trending music from configured sources.

    Supported sources: "spotify", "local".
    Falls back to curated demo data if no external APIs are configured.
    """
    if sources is None:
        sources = ["local"]

    all_songs: list[TrendingSong] = []

    for source in sources:
        if source == "spotify":
            client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
            client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

            if client_id and client_secret:
                try:
                    client = _SpotifyClient(client_id, client_secret)
                    songs = client.get_viral_tracks(limit)
                    songs = client.enrich_bpm(songs)
                    all_songs.extend(songs)
                    log.info("trending.spotify_fetched", count=len(songs))
                except Exception as exc:
                    log.warning("trending.spotify_error", error=str(exc))
            else:
                log.info("trending.spotify_not_configured")

        elif source == "local":
            local_songs = list_local_music()
            all_songs.extend(local_songs[:limit])

    if not all_songs:
        log.info("trending.using_demo_data")
        for i, demo in enumerate(_DEMO_SONGS[:limit]):
            all_songs.append(
                TrendingSong(
                    title=demo["title"],
                    artist=demo["artist"],
                    bpm=demo.get("bpm"),
                    genre=demo.get("genre"),
                    source="demo",
                    rank=i + 1,
                )
            )

    return all_songs[:limit]


async def fetch_instagram_trends(
    content_type: str | None = None,
    mood: str | None = None,
    limit: int = 20,
) -> dict:
    """
    Fetch Instagram trending content (reels, audio, hashtags).

    Uses RapidAPI if RAPIDAPI_KEY is configured; otherwise returns
    curated demo data suitable for development/testing.
    """
    rapidapi_key = os.environ.get("RAPIDAPI_KEY", "")

    if not rapidapi_key:
        log.info("trending.instagram_returning_demo")
        result = dict(_DEMO_TRENDS)
        result["source"] = "demo"
        result["fetched_at"] = datetime.now().isoformat()
        return result

    result: dict = {
        "fetched_at": datetime.now().isoformat(),
        "source": "rapidapi",
        "trending_reels": [],
        "trending_audio": [],
    }

    try:
        reels_data = _rapidapi_get("trending_reels")
        for item in reels_data.get("data", {}).get("items", [])[:limit]:
            media = item.get("media", item)
            result["trending_reels"].append({
                "caption": (media.get("caption", {}) or {}).get("text", "")[:200],
                "views": media.get("view_count", 0),
                "likes": media.get("like_count", 0),
                "audio": (media.get("clips_metadata", {}) or {}).get("original_sound_info", {}).get("original_audio_title"),
            })
    except Exception as exc:
        log.warning("trending.instagram_reels_error", error=str(exc))

    try:
        audio_data = _rapidapi_get("trending_sounds")
        for item in audio_data.get("data", {}).get("items", [])[:limit]:
            audio_info = item.get("audio", item)
            result["trending_audio"].append(
                TrendingAudio(
                    audio_id=str(audio_info.get("audio_id", "")),
                    name=audio_info.get("title", "Unknown"),
                    artist=audio_info.get("artist_name", "Unknown"),
                    use_count=audio_info.get("audio_asset_media_count", 0),
                    is_original=audio_info.get("is_original", False),
                    duration_seconds=(audio_info.get("duration_in_ms", 0) or 0) / 1000,
                    preview_url=audio_info.get("progressive_download_url"),
                    trending_rank=len(result["trending_audio"]) + 1,
                ).to_dict()
            )
    except Exception as exc:
        log.warning("trending.instagram_audio_error", error=str(exc))

    return result


async def get_music_recommendations(
    content_type: str,
    mood: str | None = None,
) -> list[dict]:
    """
    Get music recommendations based on content type and mood.

    Uses Instagram audio search when RapidAPI is configured, otherwise
    returns filtered demo suggestions.
    """
    search_terms: dict[str, list[str]] = {
        "travel": ["travel vibes", "adventure", "wanderlust"],
        "food": ["cooking", "food tiktok", "asmr"],
        "fitness": ["workout", "gym motivation"],
        "comedy": ["funny", "comedy", "meme"],
        "fashion": ["fashion", "ootd", "style"],
        "lifestyle": ["lifestyle", "aesthetic", "vlog"],
    }

    mood_terms: dict[str, list[str]] = {
        "upbeat": ["upbeat", "happy", "energetic"],
        "chill": ["chill", "relaxing", "lo-fi"],
        "dramatic": ["dramatic", "cinematic", "epic"],
        "funny": ["funny", "comedy sound"],
    }

    rapidapi_key = os.environ.get("RAPIDAPI_KEY", "")

    if rapidapi_key:
        queries = search_terms.get(content_type, ["trending"])
        if mood and mood in mood_terms:
            queries.extend(mood_terms[mood])

        all_results: list[dict] = []
        seen_ids: set[str] = set()

        for query in queries[:3]:
            try:
                data = _rapidapi_get("search_music", {"query": query})
                for item in data.get("data", {}).get("items", []):
                    aid = str(item.get("id", ""))
                    if aid in seen_ids:
                        continue
                    seen_ids.add(aid)
                    all_results.append({
                        "title": item.get("title", ""),
                        "artist": item.get("artist_name", ""),
                        "use_count": item.get("media_count", 0),
                        "preview_url": item.get("progressive_download_url"),
                        "source": "instagram",
                    })
            except Exception:
                continue

        all_results.sort(key=lambda x: x.get("use_count", 0), reverse=True)
        return all_results[:20]

    # Fallback: filter demo songs by genre/mood
    genre_map = {
        "travel": ["travel", "chill", "tropical", "acoustic"],
        "food": ["acoustic", "lofi", "pop"],
        "fitness": ["edm", "ncs", "house"],
        "comedy": ["pop", "ncs"],
        "fashion": ["house", "tropical", "pop"],
        "lifestyle": ["lofi", "chill", "acoustic"],
    }
    preferred_genres = genre_map.get(content_type, [])

    results: list[dict] = []
    for demo in _DEMO_SONGS:
        if preferred_genres and demo.get("genre") not in preferred_genres:
            continue
        results.append({
            "title": demo["title"],
            "artist": demo["artist"],
            "bpm": demo.get("bpm"),
            "genre": demo.get("genre"),
            "source": "demo",
        })

    if not results:
        results = [{"title": d["title"], "artist": d["artist"], "source": "demo"} for d in _DEMO_SONGS[:5]]

    return results


def list_local_music(music_dir: Path | None = None) -> list[TrendingSong]:
    """
    Scan a local directory for music files and return as TrendingSong list.

    Parses filenames in "Artist - Title.ext" format and reads companion
    JSON metadata files if present.
    """
    if music_dir is None:
        settings = get_settings()
        music_dir = settings.data_dir / "music"

    music_dir = Path(music_dir)
    if not music_dir.exists():
        log.debug("trending.local_music_dir_missing", path=str(music_dir))
        return []

    audio_extensions = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
    songs: list[TrendingSong] = []

    for i, audio_file in enumerate(sorted(music_dir.rglob("*"))):
        if audio_file.suffix.lower() not in audio_extensions:
            continue

        name = audio_file.stem
        if " - " in name:
            artist, title = name.split(" - ", 1)
        else:
            artist = "Unknown"
            title = name

        bpm: Optional[float] = None
        genre: Optional[str] = None

        metadata_file = audio_file.with_suffix(".json")
        if metadata_file.exists():
            try:
                meta = json.loads(metadata_file.read_text())
                bpm = meta.get("bpm")
                genre = meta.get("genre")
                title = meta.get("title", title)
                artist = meta.get("artist", artist)
            except Exception:
                pass

        songs.append(
            TrendingSong(
                title=title,
                artist=artist,
                bpm=bpm,
                genre=genre,
                source="local",
                local_path=str(audio_file),
                rank=i + 1,
            )
        )

    log.info("trending.local_scan_complete", count=len(songs), path=str(music_dir))
    return songs
