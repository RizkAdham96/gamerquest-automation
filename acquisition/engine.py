import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


INTENT_MARKERS = (
    "date de sortie",
    "plateforme",
    "plateformes",
    "comment",
    "erreur",
    "probleme",
    "problème",
    "patch",
    "performance",
    "fps",
    "crossplay",
    "sauvegarde",
    "gratuit",
    "promo",
    "reduction",
    "réduction",
    "jusqu au",
    "jusqu'au",
)

DISTRIBUTION_MARKERS = (
    "gratuit",
    "free",
    "promo",
    "reduction",
    "réduction",
    "patch",
    "erreur",
    "probleme",
    "problème",
    "performance",
    "fps",
    "date de sortie",
)

BROAD_MARKERS = {
    "gaming",
    "news",
    "actualites",
    "actualité",
    "actualités",
    "jeux video",
    "jeux vidéo",
}

STOPWORDS = {
    "a", "au", "aux", "avec", "de", "des", "du", "en", "et", "est",
    "la", "le", "les", "l", "pour", "sur", "un", "une", "the", "and",
    "game", "games", "jeu", "jeux", "video", "vidéo", "tout", "savoir",
}


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower().replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _terms(text: str) -> set[str]:
    return {
        token
        for token in _normalize(text).split()
        if len(token) > 1 and token not in STOPWORDS
    }


def _candidate_text(candidate: dict) -> str:
    return " ".join(
        [
            str(candidate.get("title", "")),
            " ".join(str(item) for item in candidate.get("keywords", []) if item),
        ]
    )


def _covered_text(article: dict) -> str:
    seo = article.get("seo", {}) if isinstance(article.get("seo"), dict) else {}
    tags = article.get("tags", []) if isinstance(article.get("tags"), list) else []
    return " ".join(
        [
            str(article.get("title", "")),
            str(article.get("slug", "")),
            str(seo.get("primary_keyword", "")),
            " ".join(str(tag) for tag in tags if tag),
        ]
    )


def _is_duplicate(candidate: dict, covered_articles: list[dict]) -> bool:
    candidate_terms = _terms(_candidate_text(candidate))
    if not candidate_terms:
        return False

    for article in covered_articles:
        existing_terms = _terms(_covered_text(article))
        if not existing_terms:
            continue
        overlap = candidate_terms & existing_terms
        shortest = min(len(candidate_terms), len(existing_terms))
        if shortest and len(overlap) >= 3 and len(overlap) / shortest >= 0.55:
            return True
    return False


def _decision(score: int, duplicate_risk: bool) -> str:
    if duplicate_risk:
        return "SKIP"
    if score >= 75:
        return "PRIORITIZE"
    if score >= 55:
        return "WATCH"
    return "SKIP"


def score_candidate(candidate: dict, covered_articles: list[dict]) -> dict:
    text = _candidate_text(candidate)
    normalized = _normalize(text)
    tokens = _terms(text)
    marker_count = sum(1 for marker in INTENT_MARKERS if _normalize(marker) in normalized)

    if len(tokens) >= 7:
        specificity = 18
    elif len(tokens) >= 5:
        specificity = 14
    elif len(tokens) >= 3:
        specificity = 8
    else:
        specificity = 2
    if marker_count >= 2:
        specificity = min(25, specificity + 7)
    elif marker_count == 1:
        specificity = min(25, specificity + 4)

    if marker_count >= 2:
        search_intent = 20
    elif marker_count == 1:
        search_intent = 14
    else:
        search_intent = 5

    freshness_label = str(candidate.get("freshness", "")).lower()
    freshness = {"urgent": 15, "fresh": 10, "evergreen": 6}.get(freshness_label, 5)

    normalized_title = _normalize(candidate.get("title", ""))
    title_terms = _terms(candidate.get("title", ""))
    is_broad = (
        len(title_terms) <= 3
        or normalized_title in BROAD_MARKERS
        or any(normalized_title == _normalize(marker) for marker in BROAD_MARKERS)
    )
    if is_broad:
        competition = 3
    elif marker_count >= 1 and len(tokens) >= 5:
        competition = 13
    else:
        competition = 8

    source_type = str(candidate.get("source_type", ""))
    gamerquest_fit = 10 if source_type in {"seo_intel", "deal"} else 7

    distribution_hits = sum(
        1 for marker in DISTRIBUTION_MARKERS if _normalize(marker) in normalized
    )
    distribution = 10 if distribution_hits >= 1 else 5

    internal_link = 5 if len(tokens) >= 4 else 2

    breakdown = {
        "specificity": specificity,
        "search_intent": search_intent,
        "freshness": freshness,
        "competition_proxy": competition,
        "gamerquest_fit": gamerquest_fit,
        "distribution_potential": distribution,
        "internal_link_potential": internal_link,
    }
    score = min(100, sum(breakdown.values()))

    duplicate_risk = _is_duplicate(candidate, covered_articles)
    decision = _decision(score, duplicate_risk)

    reasons = []
    if marker_count:
        reasons.append("clear search intent")
    if freshness >= 12:
        reasons.append("time-sensitive opportunity")
    if competition >= 12:
        reasons.append("specific long-tail angle")
    if distribution >= 10:
        reasons.append("strong social/distribution hook")
    if duplicate_risk:
        reasons.append("blocked by existing coverage")
    if not reasons:
        reasons.append("weak acquisition signal")

    result = dict(candidate)
    result.update(
        {
            "score": score,
            "decision": decision,
            "duplicate_risk": duplicate_risk,
            "breakdown": breakdown,
            "reasons": reasons,
        }
    )
    return result


def _existing_scores(root: Path) -> dict[str, dict]:
    payload = _load_json(root / "trending_seo" / "scored_topics.json", {"topics": []})
    results = {}
    for item in payload.get("topics", []) if isinstance(payload, dict) else []:
        if isinstance(item, dict) and item.get("id"):
            results[str(item["id"])] = item
    return results


def collect_candidates(root: Path) -> list[dict]:
    candidates = []
    existing_scores = _existing_scores(root)

    intel = _load_json(root / "trending_seo" / "intel" / "topics.json", {"topics": []})
    for topic in intel.get("topics", []) if isinstance(intel, dict) else []:
        if not isinstance(topic, dict):
            continue
        if str(topic.get("status", "new")).lower() != "new":
            continue
        topic_id = str(topic.get("id") or _normalize(topic.get("topic", "")).replace(" ", "-"))
        scored = existing_scores.get(topic_id, {})
        candidates.append(
            {
                "id": topic_id,
                "title": str(topic.get("topic", "")).strip(),
                "source_type": "seo_intel",
                "keywords": topic.get("keywords", []) if isinstance(topic.get("keywords"), list) else [],
                "freshness": "fresh",
                "existing_score": int(scored.get("total_score", 0) or 0),
                "sources": topic.get("sources", []) if isinstance(topic.get("sources"), list) else [],
            }
        )

    deals = _load_json(root / "gamerquest-deals-feed.json", {"articles": []})
    for article in deals.get("articles", []) if isinstance(deals, dict) else []:
        if not isinstance(article, dict):
            continue
        deal = article.get("deal", {}) if isinstance(article.get("deal"), dict) else {}
        current_price = deal.get("current_price")
        expires_at = deal.get("expires_at")
        urgent = current_price == 0 or bool(expires_at)
        game = str(deal.get("game", "")).strip()
        store = str(deal.get("store", "")).strip()
        candidates.append(
            {
                "id": str(article.get("source_id") or _normalize(article.get("title", "")).replace(" ", "-")),
                "title": str(article.get("title", "")).strip(),
                "source_type": "deal",
                "keywords": [item for item in (game, store, f"{game} gratuit" if current_price == 0 else "") if item],
                "freshness": "urgent" if urgent else "fresh",
                "existing_score": 0,
                "sources": [{"type": _normalize(store) or "deal", "url": article.get("source_url", "")}],
            }
        )

    return candidates


def _covered_articles(root: Path) -> list[dict]:
    covered = []
    news_feed = _load_json(root / "gamerquest-news-feed.json", {"articles": []})
    history = _load_json(root / "state" / "news_topic_history.json", {"articles": []})
    for payload in (news_feed, history):
        if not isinstance(payload, dict):
            continue
        for article in payload.get("articles", []):
            if isinstance(article, dict):
                covered.append(article)
    return covered


def build_shadow_queue(root: Path) -> dict:
    root = Path(root)
    covered = _covered_articles(root)
    scored = [score_candidate(candidate, covered) for candidate in collect_candidates(root)]
    scored.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("title", ""))))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "shadow",
        "count": len(scored),
        "opportunities": scored,
    }


def write_shadow_queue(root: Path, output_path: Path | None = None) -> dict:
    root = Path(root)
    payload = build_shadow_queue(root)
    target = output_path or (root / "acquisition" / "shadow_queue.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
