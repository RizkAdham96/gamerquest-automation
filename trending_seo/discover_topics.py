from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from researcher import PUBLIC_GAMING_FEEDS, extract_feed_entries, fetch_feed


BASE_DIR = Path(__file__).resolve().parent
INTEL_FILE = BASE_DIR / "intel" / "topics.json"
SCORED_FILE = BASE_DIR / "scored_topics.json"
INTENT_HISTORY_FILE = BASE_DIR / "seo_intent_history.json"

MAX_NEW_TOPICS_PER_RUN = 12
MAX_INTEL_TOPICS = 250


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return data if isinstance(data, dict) else default


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def normalize(value: str) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9à-ÿ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def topic_id(title: str, url: str) -> str:
    digest = hashlib.sha1(
        f"{normalize(title)}|{str(url).strip().lower()}".encode("utf-8")
    ).hexdigest()[:12]
    slug = re.sub(r"[^a-z0-9]+", "-", normalize(title)).strip("-")[:55]
    return f"rss-{slug or 'gaming'}-{digest}"


def build_keywords(title: str) -> list[str]:
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    variants = [
        title,
        f"{title} date de sortie",
        f"{title} plateformes",
        f"{title} gameplay",
        f"{title} guide",
        f"{title} avis",
    ]
    output = []
    seen = set()
    for item in variants:
        key = normalize(item)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def existing_keys(intel: dict, scored: dict, history: dict) -> tuple[set[str], set[str]]:
    titles: set[str] = set()
    urls: set[str] = set()

    for item in intel.get("topics", []):
        if not isinstance(item, dict):
            continue
        title = normalize(item.get("topic", ""))
        if title:
            titles.add(title)
        for source in item.get("sources", []):
            if isinstance(source, dict) and source.get("url"):
                urls.add(str(source["url"]).strip().lower().rstrip("/"))

    for item in scored.get("topics", []):
        if isinstance(item, dict):
            title = normalize(item.get("topic", ""))
            if title:
                titles.add(title)

    for item in history.get("published", []):
        if not isinstance(item, dict):
            continue
        for value in (item.get("title", ""), item.get("primary_keyword", "")):
            key = normalize(value)
            if key:
                titles.add(key)

    return titles, urls


def build_topic(entry: dict, publisher: str) -> dict | None:
    title = re.sub(r"\s+", " ", str(entry.get("title", "") or "")).strip()
    url = str(entry.get("url", "") or "").strip()
    description = re.sub(
        r"\s+",
        " ",
        str(entry.get("description", "") or ""),
    ).strip()

    if len(title) < 12 or not url.startswith(("http://", "https://")):
        return None

    evidence = description[:1200] or (
        f"{publisher} published a fresh gaming story titled: {title}. "
        "All factual claims must be independently verified before publication."
    )

    return {
        "id": topic_id(title, url),
        "topic": title,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "region": "FR",
        "sources": [
            {
                "type": "publisher",
                "url": url,
                "title": title,
                "evidence": evidence,
            }
        ],
        "keywords": build_keywords(title),
        "notes": (
            "Automatically discovered from a current gaming publisher feed. "
            "Treat the source as a lead: verify material claims and choose a "
            "specific French search intent before publishing."
        ),
        "status": "new",
    }


def discover() -> dict:
    intel = load_json(
        INTEL_FILE,
        {"version": "1.1", "updated_at": None, "topics": []},
    )
    scored = load_json(SCORED_FILE, {"topics": []})
    history = load_json(INTENT_HISTORY_FILE, {"published": []})

    known_titles, known_urls = existing_keys(intel, scored, history)
    fresh = []

    for feed in PUBLIC_GAMING_FEEDS:
        if len(fresh) >= MAX_NEW_TOPICS_PER_RUN:
            break

        feed_text = fetch_feed(feed["url"])
        if not feed_text:
            continue

        for entry in extract_feed_entries(feed_text):
            if len(fresh) >= MAX_NEW_TOPICS_PER_RUN:
                break

            title_key = normalize(entry.get("title", ""))
            url_key = str(entry.get("url", "")).strip().lower().rstrip("/")

            if not title_key or title_key in known_titles or url_key in known_urls:
                continue

            topic = build_topic(entry, feed.get("publisher", "Gaming publisher"))
            if topic is None:
                continue

            fresh.append(topic)
            known_titles.add(title_key)
            known_urls.add(url_key)

    topics = [
        item
        for item in intel.get("topics", [])
        if isinstance(item, dict)
    ]
    topics.extend(fresh)

    # Keep a bounded durable inventory. Scored IDs remain durable elsewhere.
    if len(topics) > MAX_INTEL_TOPICS:
        topics = topics[-MAX_INTEL_TOPICS:]

    result = {
        "version": "1.1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "topics": topics,
    }
    save_json(INTEL_FILE, result)

    print("===================================")
    print("GAMERQUEST SEO TOPIC DISCOVERY")
    print("===================================")
    print(f"Added topics: {len(fresh)}")
    print(f"Intel inventory: {len(topics)}")

    for index, item in enumerate(fresh, start=1):
        print(f"{index}. {item.get('topic')}")

    return result


if __name__ == "__main__":
    discover()
