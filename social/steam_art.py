"""Official Steam screenshots for the game a social source is about.

A news article usually exposes a single hero image, so a three-slide carousel
either could not be built or borrowed artwork from other articles. The game's
own store gallery is relevant by construction and published at full
resolution.
"""

from __future__ import annotations

import re

from reviews.discovery import BLOCKED_TAGS
from reviews.steam import _norm, fetch_app_details, search_game

MAX_NAME_LOOKUPS = 2
MAX_SCREENSHOTS = 6
MIN_NAME_CHARS = 4

_CACHE: dict[str, list[str]] = {}


def _clean(value) -> str:
    # str.split() also splits on the no-break spaces French tags contain.
    return " ".join(str(value or "").split())


def candidate_game_names(item) -> list[str]:
    """Names the article is unmistakably about.

    A deal names its game outright. For news, the game must be the whole
    subject before the title's separator ("Grounded 2 – notes de mise à
    jour"): a name that is only part of it is usually a franchise, and
    "Final Fantasy VII" would otherwise supply 1997 screenshots for
    "Final Fantasy VII Revelation".
    """
    if not isinstance(item, dict):
        return []

    names = []
    deal = item.get("deal")
    if isinstance(deal, dict):
        names.append(_clean(deal.get("game")))

    title = _clean(item.get("title"))
    head = _clean(re.split(r"\s[:–—|-]\s", title, maxsplit=1)[0])
    if head != title:
        names.append(head)

    seen = set()
    output = []
    for name in names:
        key = _norm(name)
        if len(key) < MIN_NAME_CHARS or key in seen or name.lower() in BLOCKED_TAGS:
            continue
        seen.add(key)
        output.append(name)
    return output


def _screenshots(details) -> list[str]:
    urls = []
    for shot in (details or {}).get("screenshots") or []:
        url = str(shot.get("path_full", "")) if isinstance(shot, dict) else ""
        if url.startswith("https://") and url not in urls:
            urls.append(url)
    return urls[:MAX_SCREENSHOTS]


def steam_screenshots_for_item(item, search=search_game, fetch_details=fetch_app_details) -> list[str]:
    """Return the store gallery of the item's game, or [] when it is not on Steam.

    Lookups never raise: Steam being unreachable must leave the carousel on
    its existing image sources, not stop the run.
    """
    for name in candidate_game_names(item)[:MAX_NAME_LOOKUPS]:
        key = _norm(name)
        if key in _CACHE:
            if _CACHE[key]:
                return list(_CACHE[key])
            continue
        try:
            match = search(name)
            details = fetch_details(int(match["id"])) if match else None
        except Exception as exc:
            print(f"WARNING: Steam artwork lookup failed for {name}: {exc}")
            continue
        shots = _screenshots(details) if details and details.get("type") == "game" else []
        _CACHE[key] = shots
        if shots:
            return list(shots)
    return []
