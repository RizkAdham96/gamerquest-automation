from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "automation.py"
TESTS = ROOT / "test_news_quality_guards.py"
HISTORY = ROOT / "state" / "news_topic_history.json"

TEST_MARKER = "def test_historical_topic_history_blocks_old_wordpress_duplicate"

TEST_BLOCK = r'''


def test_historical_topic_history_blocks_old_wordpress_duplicate(monkeypatch, tmp_path):
    history_file = tmp_path / "news_topic_history.json"
    history_file.write_text(
        '{"articles":[{"title":"Warlock (2027) : date de sortie, plateformes et aperçu du gameplay","slug":"warlock-date-de-sortie","content":"","seo":{"primary_keyword":"Warlock date de sortie"},"tags":[]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(automation, "NEWS_TOPIC_HISTORY_FILE", history_file)
    monkeypatch.setattr(
        automation,
        "load_existing_news_feed",
        lambda: {"articles": []},
    )
    candidate = (
        "Warlock : date de sortie et plateformes",
        "meta",
        "Warlock date de sortie",
        "Warlock plateformes",
        "Informational",
        "warlock-date-sortie-plateformes",
        "Warlock : date de sortie, plateformes et gameplay",
        "excerpt",
        "Actualités",
        "Warlock",
        "Les informations de sortie et de plateformes sont détaillées.",
    )
    assert automation.news_quality_rejection(candidate)


def test_remember_news_topic_persists_new_topic(monkeypatch, tmp_path):
    history_file = tmp_path / "news_topic_history.json"
    monkeypatch.setattr(automation, "NEWS_TOPIC_HISTORY_FILE", history_file)
    item = article(
        "Project Nova : date de sortie",
        "project-nova-date-sortie",
    )
    automation.remember_news_topic(item)
    loaded = automation.load_news_topic_history()
    assert loaded[0]["slug"] == "project-nova-date-sortie"
'''

HELPER_BLOCK = r'''

def load_news_topic_history():
    """Load compact topic history kept beyond the rolling 50-item feed."""
    if not NEWS_TOPIC_HISTORY_FILE.exists():
        return []

    try:
        data = json.loads(
            NEWS_TOPIC_HISTORY_FILE.read_text(encoding="utf-8")
        )
        articles = data.get("articles", []) if isinstance(data, dict) else data
        if not isinstance(articles, list):
            return []
        return [item for item in articles if isinstance(item, dict)]
    except Exception as error:
        print(f"WARNING: News topic history could not be loaded: {error}")
        return []


def combined_news_quality_history():
    """Merge rolling feed + long-lived topic history without duplicates."""
    feed_articles = load_existing_news_feed().get("articles", [])
    history_articles = load_news_topic_history()
    merged = []
    seen = set()

    for item in [*feed_articles, *history_articles]:
        key = slugify(item.get("slug", "") or item.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)

    return merged


def remember_news_topic(article):
    """Persist a compact record so old published topics do not reappear later."""
    STATE_FOLDER.mkdir(exist_ok=True)
    history = load_news_topic_history()

    article_seo = article.get("seo", {})
    if not isinstance(article_seo, dict):
        article_seo = {}

    compact = {
        "title": str(article.get("title", "")).strip(),
        "slug": str(article.get("slug", "")).strip(),
        "content": str(article.get("content", ""))[:3000],
        "tags": article.get("tags", []) if isinstance(article.get("tags", []), list) else [],
        "seo": {
            "primary_keyword": str(article_seo.get("primary_keyword", "")).strip(),
        },
    }

    compact_key = slugify(compact["slug"] or compact["title"])
    remaining = []
    for item in history:
        item_key = slugify(item.get("slug", "") or item.get("title", ""))
        if item_key and item_key == compact_key:
            continue
        remaining.append(item)

    payload = {
        "articles": [compact, *remaining][:MAX_NEWS_TOPIC_HISTORY]
    }
    NEWS_TOPIC_HISTORY_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


'''

SEEDS = [
    ("Nintendo Direct septembre 2026 : récapitulatif complet des annonces, dates de sortie et plateformes", "nintendo-direct-septembre-2026-annonces"),
    ("Date de sortie du remake Ocarina of Time sur Switch 2 – Analyse du Direct 40e anniversaire de Zelda", "date-sortie-ocarina-of-time-switch-2"),
    ("The Witcher 3 Remastered : tout ce qu’on sait après l’annonce à Gamescom 2026 (date, nouveautés, plateformes)", "the-witcher-3-remastered-tout-ce-quon-sait-apres-lannonce-a-gamescom-2026-date-nouveautes-plateformes"),
    ("Wo Long Complete Edition arrive sur Switch 2 : performance en deçà des rivaux", "wo-long-complete-edition-switch-2-performance"),
    ("Calendrier des sorties Nintendo Switch 2 2026 : dates officielles", "dates-sortie-switch-2-2026"),
    ("Final Fantasy VII Revelation : date de sortie, plateformes, prix et DLC – tout ce qu’il faut savoir", "final-fantasy-vii-revelation-sortie-plateformes-prix-dlc"),
    ("Final Fantasy VII Revelation : date de sortie, plateformes, prix et premières infos gameplay", "final-fantasy-vii-revelation-2027"),
    ("Final Fantasy VII Revelation : date de sortie, trailer et gameplay du State Play septembre 2026", "final-fantasy-vii-revelation-date-sortie-2027"),
    ("Final Fantasy 7 Revelation : tout ce qu’on sait de la sortie après Gamescom 2026", "final-fantasy-7-revelation-dates-sortie"),
    ("State of Play septembre 2026 : toutes les annonces, dates de sortie et plateformes", "state-of-play-septembre-2026-annonces"),
    ("State of Play et State of Play Japan le 3 septembre 2026 : date, heure et plateformes de diffusion", "state-of-play-septembre-2026"),
    ("Dates de sortie Xbox : tout ce que révèle le State of Play de septembre 2026", "dates-de-sortie-xbox-state-of-play-sept-2026"),
    ("Dates de sortie Xbox 2027 : tout ce qui a été annoncé au State of Play de septembre 2026", "dates-sortie-xbox-2027-state-of-play-2026"),
    ("Gamescom Opening Night Live 2026 : tout ce qu’on sait des dates, plateformes et gameplay", "gamescom-opening-night-live-2026"),
    ("Dates de sortie et plateformes des jeux présentés à Gamescom Opening Night Live 2026", "dates-sortie-jeux-gamescom-2026-2"),
    ("Toutes les dates de sortie des jeux annoncés à Gamescom Opening Night Live 2026", "dates-sortie-jeux-gamescom-2026"),
    ("Gamescom 2026 : dates de sortie et infos sur les 7 jeux les plus attendus", "gamescom-2026-7-jeux-attendus"),
    ("The Witcher 3 Remastered : date de sortie, plateformes, prix et nouveautés", "witcher-3-remastered-2026"),
    ("Witcher 3 Remaster : date, plateformes, prix et premières infos sur l’extension Songs of the Past", "witcher-3-remaster-songs-of-the-past"),
    ("The Witcher 3 : les DLC Blood and Wine et Hearts of Stone sont gratuits avant le remaster", "witcher-3-remaster-dlc-gratuit"),
    ("Warlock (D&D) : tout ce que l’on sait sur la date de sortie, les plateformes et le gameplay", "warlock-date-de-sortie-2"),
    ("Warlock (2027) : date de sortie, plateformes et aperçu du gameplay", "warlock-date-de-sortie"),
    ("Exodus : la date de sortie officielle, les plateformes et le gameplay dévoilés à la Gamescom 2026", "exodus-date-de-sortie-2027"),
    ("Exodus : date de sortie, plateformes et aperçu du gameplay", "exodus-date-de-sortie-plateformes-gameplay"),
    ("Tout ce qu’on sait du DLC « Charting the Unknown » de Crimson Desert", "crimson-desert-dlc-charting-unknown"),
    ("Crimson Desert : l'extension « Chartering the Unknown » sort le 15 octobre 2026", "crimson-desert-extension-date-sortie"),
    ("Stellar Blade sur Nintendo Switch 2 : tout ce qu’on sait sur la sortie, les plateformes et le gameplay", "stellar-blade-switch-2-date-sortie"),
    ("Call of Duty : Modern Warfare 4 – tout savoir sur la version Switch 2 : date, plateformes et gameplay", "call-of-duty-modern-warfare-4-switch-2"),
    ("Modern Warfare 4 : rumeurs sur un patch beta avec la carte Cachette et le mode Inflation", "mise-a-jour-beta-modern-warfare-4-rumeurs"),
    ("Minecraft Dungeons II : date de sortie, plateformes et aperçu du trailer", "minecraft-dungeons-ii-date-de-sortie"),
    ("Black Myth : Zhong Kui – Analyse du gameplay du trailer de 15 minutes", "black-myth-zhong-kui-gameplay-trailer"),
    ("PS5 Pro vs Xbox Series X vs Switch 2 – prix, spécifications et guide d’achat 2026", "ps5-pro-xbox-series-x-switch-2-2026"),
]


def run_tests(expect_failure: bool) -> None:
    env = os.environ.copy()
    env.setdefault("GROQ_API_KEY", "test-key")
    env.setdefault("TAVILY_API_KEY", "test-key")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "test_news_quality_guards.py", "-q"],
        cwd=ROOT,
        env=env,
        check=False,
    )
    if expect_failure and result.returncode == 0:
        raise SystemExit("RED phase unexpectedly passed")
    if not expect_failure and result.returncode != 0:
        raise SystemExit(result.returncode)


def add_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    if TEST_MARKER not in text:
        TESTS.write_text(text + TEST_BLOCK, encoding="utf-8")


def patch_production() -> None:
    text = AUTOMATION.read_text(encoding="utf-8")

    if "NEWS_TOPIC_HISTORY_FILE =" not in text:
        text = text.replace(
            'TAVILY_STATE_FILE = STATE_FOLDER / "tavily_usage.json"\n',
            'TAVILY_STATE_FILE = STATE_FOLDER / "tavily_usage.json"\nNEWS_TOPIC_HISTORY_FILE = STATE_FOLDER / "news_topic_history.json"\nMAX_NEWS_TOPIC_HISTORY = 1000\n',
            1,
        )

    if "def load_news_topic_history():" not in text:
        marker = "def build_news_feed_article(\n"
        if marker not in text:
            raise SystemExit("build_news_feed_article marker not found")
        text = text.replace(marker, HELPER_BLOCK + marker, 1)

    old = '    if existing_articles is None:\n        existing_articles = load_existing_news_feed().get("articles", [])\n'
    new = '    if existing_articles is None:\n        existing_articles = combined_news_quality_history()\n'
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise SystemExit("news_quality_rejection block not found")

    write_marker = '''    NEWS_FEED_FILE.write_text(\n        json.dumps(\n            updated_feed,\n            ensure_ascii=False,\n            indent=2,\n        ),\n        encoding="utf-8",\n    )\n'''
    if "remember_news_topic(new_article)" not in text:
        if write_marker not in text:
            raise SystemExit("feed write marker not found")
        text = text.replace(
            write_marker,
            write_marker + "\n    remember_news_topic(new_article)\n",
            1,
        )

    AUTOMATION.write_text(text, encoding="utf-8")


def seed_history() -> None:
    existing = []
    if HISTORY.exists():
        try:
            data = json.loads(HISTORY.read_text(encoding="utf-8"))
            existing = data.get("articles", []) if isinstance(data, dict) else []
        except Exception:
            existing = []

    by_slug = {
        item.get("slug"): item
        for item in existing
        if isinstance(item, dict) and item.get("slug")
    }
    for title, slug in SEEDS:
        by_slug.setdefault(
            slug,
            {
                "title": title,
                "slug": slug,
                "content": "",
                "tags": [],
                "seo": {"primary_keyword": title},
            },
        )

    HISTORY.parent.mkdir(exist_ok=True)
    HISTORY.write_text(
        json.dumps({"articles": list(by_slug.values())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    add_tests()
    run_tests(expect_failure=True)
    print("RED phase failed as expected.")
    patch_production()
    seed_history()
    run_tests(expect_failure=False)
    print("GREEN phase passed.")


if __name__ == "__main__":
    main()
