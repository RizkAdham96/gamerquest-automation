"""Evergreen SEO topics built from official Steam store data.

Publisher RSS headlines almost never carry a durable French search intent, so
the scorer rejects them and the SEO pipeline has nothing to write. This module
feeds it questions players actually type ("configuration pc <jeu>",
"<jeu> multijoueur") together with the store facts needed to answer them, so
no article depends on the model guessing a specification or a game mode.
"""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from reviews.discovery import STARTER_GAMES
from reviews.steam import fetch_app_details, search_game

DEALS_FEED = ROOT_DIR / "gamerquest-deals-feed.json"

TOPIC_ID_PREFIX = "evg-"
EVIDENCE_ORIGIN = "steam_store_api"
MAX_NEW_EVERGREEN_TOPICS_PER_RUN = 4
MAX_STEAM_LOOKUPS_PER_RUN = 6
MIN_REQUIREMENTS_CHARS = 60


def is_evergreen_topic(topic) -> bool:
    return isinstance(topic, dict) and str(topic.get("id", "")).startswith(
        TOPIC_ID_PREFIX
    )


def normalize(value) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9à-ÿ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_store_html(value) -> str:
    text = re.sub(r"<br\s*/?>|</li>|</p>", " ; ", str(value or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(\s*;\s*)+", " ; ", text)
    return text.strip(" ;")


def config_keyword(game: str) -> str:
    return f"configuration pc {game}"


def multiplayer_keyword(game: str) -> str:
    return f"{game} multijoueur"


def candidate_games(deals_feed=None) -> list[str]:
    """Games GamerQuest already covers first, then the curated catalog."""
    if deals_feed is None:
        try:
            deals_feed = json.loads(DEALS_FEED.read_text(encoding="utf-8"))
        except Exception:
            deals_feed = {}

    names = []
    for article in deals_feed.get("articles", []) if isinstance(deals_feed, dict) else []:
        game = (article.get("deal") or {}).get("game", "") if isinstance(article, dict) else ""
        names.append(" ".join(str(game or "").split()))
    names.extend(STARTER_GAMES)

    seen = set()
    output = []
    for name in names:
        key = normalize(name)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(name)
    return output


def _names(items) -> str:
    return ", ".join(
        str(item.get("description", "")).strip()
        for item in items or []
        if isinstance(item, dict) and str(item.get("description", "")).strip()
    )


def build_store_facts(details: dict) -> str:
    """Shared factual header: every value is copied from the store record."""
    parts = [
        f"Données officielles de la fiche Steam de {details.get('name', '')}, "
        f"consultée le {datetime.now(timezone.utc).date().isoformat()}."
    ]
    developers = ", ".join(str(item) for item in details.get("developers") or [])
    publishers = ", ".join(str(item) for item in details.get("publishers") or [])
    if developers:
        parts.append(f"Développeur : {developers}.")
    if publishers:
        parts.append(f"Éditeur : {publishers}.")
    release = details.get("release_date") or {}
    if release.get("date"):
        label = "Sortie prévue sur Steam" if release.get("coming_soon") else "Date de sortie sur Steam"
        parts.append(f"{label} : {release['date']}.")
    genres = _names(details.get("genres"))
    if genres:
        parts.append(f"Genres : {genres}.")
    platforms = details.get("platforms") or {}
    systems = [
        label
        for key, label in (("windows", "Windows"), ("mac", "macOS"), ("linux", "Linux"))
        if platforms.get(key)
    ]
    if systems:
        parts.append(f"Systèmes pris en charge sur Steam : {', '.join(systems)}.")
    return " ".join(parts)


def build_config_evidence(details: dict) -> str:
    requirements = details.get("pc_requirements")
    if not isinstance(requirements, dict):
        return ""
    minimum = clean_store_html(requirements.get("minimum"))
    recommended = clean_store_html(requirements.get("recommended"))
    if len(minimum) < MIN_REQUIREMENTS_CHARS:
        return ""
    parts = [build_store_facts(details), f"Configuration PC {minimum}."]
    if recommended:
        parts.append(f"Configuration PC {recommended}.")
    else:
        parts.append("La fiche Steam n'indique pas de configuration recommandée.")
    return " ".join(parts)


def build_multiplayer_evidence(details: dict) -> str:
    categories = _names(details.get("categories"))
    if not categories:
        return ""
    parts = [
        build_store_facts(details),
        f"Modes et fonctionnalités déclarés sur Steam : {categories}.",
        "Seuls les modes de cette liste sont confirmés ; un mode absent de la "
        "liste n'est pas annoncé sur la fiche Steam.",
    ]
    controller = str(details.get("controller_support") or "").strip().lower()
    if controller == "full":
        parts.append("Prise en charge des manettes : complète.")
    elif controller == "partial":
        parts.append("Prise en charge des manettes : partielle.")
    description = clean_store_html(details.get("short_description"))
    if description:
        parts.append(f"Présentation officielle : {description}")
    return " ".join(parts)


def _featured_image(details: dict) -> str:
    for shot in details.get("screenshots") or []:
        if isinstance(shot, dict) and str(shot.get("path_full", "")).startswith("https://"):
            return str(shot["path_full"])
    image = str(details.get("header_image") or "")
    return image if image.startswith("https://") else ""


def _topic(intent: str, game: str, details: dict, title: str, keyword: str, evidence: str) -> dict:
    appid = int(details["steam_appid"])
    return {
        "id": f"{TOPIC_ID_PREFIX}{intent}-{appid}",
        "topic": title,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "region": "FR",
        "sources": [
            {
                "type": "store",
                "url": f"https://store.steampowered.com/app/{appid}/",
                "title": f"{details.get('name', game)} sur Steam",
                "evidence": evidence,
                "evidence_origin": EVIDENCE_ORIGIN,
                "image_url": _featured_image(details),
            }
        ],
        "keywords": [keyword, f"{game} PC", f"{game} Steam"],
        "notes": (
            "Evergreen search intent generated from official Steam store data. "
            "Specifications and game modes must be taken from the source evidence only."
        ),
        "status": "new",
    }


def build_game_topics(game: str, details: dict) -> list[dict]:
    topics = []
    config = build_config_evidence(details)
    if config:
        topics.append(_topic(
            "config", game, details,
            f"Configuration PC {game} : minimale, recommandée et conseils",
            config_keyword(game),
            config,
        ))
    multiplayer = build_multiplayer_evidence(details)
    if multiplayer:
        topics.append(_topic(
            "multi", game, details,
            f"{game} multijoueur : coop, en ligne et modes de jeu",
            multiplayer_keyword(game),
            multiplayer,
        ))
    return topics


def discover_evergreen_topics(
    known_keywords: set[str],
    checked_games: set[str],
    games=None,
    search=search_game,
    fetch_details=fetch_app_details,
    max_topics: int = MAX_NEW_EVERGREEN_TOPICS_PER_RUN,
    max_lookups: int = MAX_STEAM_LOOKUPS_PER_RUN,
) -> list[dict]:
    """Return new topics; `checked_games` is updated so no game is looked up twice."""
    fresh = []
    lookups = 0

    for game in games if games is not None else candidate_games():
        if len(fresh) >= max_topics or lookups >= max_lookups:
            break
        game_key = normalize(game)
        # Remembering every resolved game keeps unmatched titles at the head of
        # the list from consuming the lookup allowance on every run.
        if game_key in checked_games:
            continue

        lookups += 1
        try:
            match = search(game)
            details = fetch_details(int(match["id"])) if match else None
        except Exception as error:
            print(f"Evergreen lookup failed for {game}: {error}")
            continue
        checked_games.add(game_key)
        if not details or details.get("type") != "game":
            continue

        for topic in build_game_topics(game, details):
            keyword = normalize(topic["keywords"][0])
            if keyword in known_keywords:
                continue
            fresh.append(topic)
            known_keywords.add(keyword)

    return fresh
