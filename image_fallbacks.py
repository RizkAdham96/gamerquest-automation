"""Extra artwork sources used before the plain GamerQuest fallback.

When a source page has no usable social image (YouTube links, pages that
block bots, roundups whose artwork shows another game), the News featured
image used to be an empty dark gradient. These helpers find real artwork:

1. the YouTube video thumbnail when the source is a YouTube video;
2. the game's official Steam artwork, looked up from the article title.

Both use free public endpoints and need no API key.
"""

import re
import unicodedata
from urllib.parse import parse_qs, urlparse

import requests

USER_AGENT = "Mozilla/5.0 (compatible; GamerQuestFR/1.0)"
STEAM_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
STEAM_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_ASSET_URL = (
    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/"
    "{app_id}/{name}"
)

# Words that describe the article, not the game.
TITLE_NOISE = {
    "date", "sortie", "de", "du", "des", "la", "le", "les", "et", "sur",
    "en", "pour", "a", "au", "aux", "un", "une", "tout", "savoir",
    "plateformes", "prix", "gameplay", "trailer", "dlc", "patch", "notes",
    "mise", "jour", "maj", "edition", "remaster", "remastered",
}


def _norm_tokens(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode(
        "ascii", "ignore"
    ).decode("ascii").lower()
    text = text.replace("&", " and ")
    return [token for token in re.findall(r"[a-z0-9]+", text) if token]


def youtube_video_id(url):
    """Return the video id of a YouTube watch/short/embed/youtu.be URL."""
    try:
        parsed = urlparse(str(url or ""))
    except Exception:
        return ""
    host = parsed.netloc.lower().replace("www.", "").replace("m.", "")
    candidate = ""
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if parsed.path == "/watch":
            candidate = (parse_qs(parsed.query).get("v") or [""])[0]
        else:
            match = re.match(r"^/(?:shorts|embed|live|v)/([^/?#]+)", parsed.path)
            candidate = match.group(1) if match else ""
    return candidate if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else ""


def youtube_thumbnail_candidates(url):
    video_id = youtube_video_id(url)
    if not video_id:
        return []
    return [
        f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
    ]


def game_name_from_title(article_title):
    """Best guess at the game name: the part of the title before ':' / '–'.

    "Neon Abyss 2 : date de sortie, plateformes" -> "Neon Abyss 2"
    """
    title = str(article_title or "").strip()
    head = re.split(r"\s*(?::|–|—|\s-\s|\|)\s*", title, maxsplit=1)[0]
    head = re.sub(r"[«»\"“”]", "", head).strip()
    return head


def _significant(tokens):
    return [token for token in tokens if token not in TITLE_NOISE]


def steam_name_matches(query_name, steam_name):
    """True when the Steam app name is the game the title is about."""
    query = _significant(_norm_tokens(query_name))
    found = _significant(_norm_tokens(steam_name))
    if not query or not found:
        return False
    query_set, found_set = set(query), set(found)
    # Every word of the game name must be in the Steam name, and the Steam
    # name may only add a little (e.g. a subtitle word), so "Neon Abyss 2"
    # does not match "Neon Abyss" and "Hades" does not match "Hades II".
    if not query_set <= found_set:
        return False
    extra = found_set - query_set
    # A sequel number is a different game ("Hades" vs "Hades II").
    if any(re.fullmatch(r"\d+|[ivx]+", token) for token in extra):
        return False
    return len(extra) <= 1


def steam_app_id(game_name, session=None, timeout=20):
    if len(_significant(_norm_tokens(game_name))) == 0:
        return None
    http = session or requests
    try:
        response = http.get(
            STEAM_SEARCH_URL,
            params={"term": game_name, "cc": "fr", "l": "french"},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        response.raise_for_status()
        items = response.json().get("items") or []
    except Exception:
        return None
    for item in items[:5]:
        if steam_name_matches(game_name, item.get("name", "")):
            return item.get("id")
    return None


def steam_artwork_candidates(article_title, session=None, timeout=20):
    """Wide official artwork for the game named in the title, best first."""
    app_id = steam_app_id(game_name_from_title(article_title), session, timeout)
    if not app_id:
        return []
    candidates = [
        STEAM_ASSET_URL.format(app_id=app_id, name="library_hero.jpg"),
    ]
    http = session or requests
    try:
        response = http.get(
            STEAM_DETAILS_URL,
            params={"appids": app_id, "l": "french"},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        data = (response.json().get(str(app_id)) or {}).get("data") or {}
        for shot in (data.get("screenshots") or [])[:2]:
            if shot.get("path_full"):
                candidates.append(shot["path_full"])
        if data.get("header_image"):
            candidates.append(data["header_image"])
    except Exception:
        pass
    candidates.append(STEAM_ASSET_URL.format(app_id=app_id, name="header.jpg"))
    return candidates
