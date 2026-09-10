import json
from pathlib import Path

NEWS_FEED = Path("gamerquest-news-feed.json")
DEALS_FEED = Path("gamerquest-deals-feed.json")

STARTER_GAMES = [
    "Elden Ring",
    "Cyberpunk 2077",
    "Baldur's Gate 3",
    "Clair Obscur: Expedition 33",
    "Red Dead Redemption 2",
    "Hades",
    "Hades II",
    "Helldivers 2",
    "Hogwarts Legacy",
    "Resident Evil 4",
    "Resident Evil Village",
    "Dead Space",
    "The Witcher 3: Wild Hunt",
    "Sekiro: Shadows Die Twice",
    "Dark Souls III",
    "Monster Hunter Wilds",
    "Monster Hunter: World",
    "No Man's Sky",
    "Stardew Valley",
    "Hollow Knight",
    "Hollow Knight: Silksong",
    "God of War",
    "God of War Ragnarök",
    "Marvel's Spider-Man Remastered",
    "Ghost of Tsushima DIRECTOR'S CUT",
]

ALIASES = {
    "wo long": "Wo Long: Fallen Dynasty",
}

BLOCKED_TAGS = {
    "ps5", "ps4", "xbox", "xbox series", "xbox series x", "xbox series s",
    "pc", "steam", "epic", "epic games", "nintendo", "nintendo switch",
    "nintendo switch 2", "switch 2", "switch", "dlc", "update", "patch",
    "playstation", "game pass", "xbox game pass", "gamescom", "state of play",
}


def _load(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _clean_candidate(value):
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    key = text.lower()
    if key in BLOCKED_TAGS:
        return ""
    return ALIASES.get(key, text)


def discover_game_queries(news_feed=None, deals_feed=None, limit=15):
    news_feed = news_feed if news_feed is not None else _load(NEWS_FEED)
    deals_feed = deals_feed if deals_feed is not None else _load(DEALS_FEED)
    candidates = []

    for article in deals_feed.get("articles", []):
        game = _clean_candidate((article.get("deal") or {}).get("game", ""))
        if game:
            candidates.append(game)

    for article in news_feed.get("articles", []):
        for tag in article.get("tags") or []:
            game = _clean_candidate(tag)
            if game:
                candidates.append(game)

    # Keep GamerQuest's own current games first, then fill the category with
    # a curated evergreen starter catalog so Tests & Avis is useful from day one.
    candidates.extend(STARTER_GAMES)

    seen = set()
    result = []
    for value in candidates:
        key = " ".join(value.lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= limit:
            break
    return result
