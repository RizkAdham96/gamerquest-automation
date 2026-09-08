"""GamerQuest evergreen SEO selection and quality rules."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List

SEO_ENGINE_VERSION = "2.0"

EVENT_ONLY_TERMS = {
    "annonce", "annonces", "showcase", "state of play", "gamescom",
    "direct", "trailer", "conference", "livestream", "event",
}

EVERGREEN_PATTERNS = (
    "meilleurs ", "meilleures ", "jeux comme ", "comment ",
    "crossplay", "configuration pc", "duree de vie", "ordre pour jouer",
    "vaut il le coup", "alternatives a", "guide ", "astuces ",
)

INTENT_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "d", "a",
    "au", "aux", "sur", "pour", "en", "et", "dans", "avec",
}

INTENT_TOKEN_ALIASES = {
    "cooperatif": "coop",
    "cooperatifs": "coop",
    "cooperative": "coop",
    "cooperatives": "coop",
    "coop": "coop",
}


def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _ascii_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _clean_text(value).lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _normalize_keyword(value: Any) -> str:
    return " ".join(_clean_text(value).lower().split())


def _contains_keyword(text: str, keyword: str) -> bool:
    return bool(_normalize_keyword(keyword)) and _normalize_keyword(keyword) in _normalize_keyword(text)


def _primary_keyword(topic: Dict[str, Any]) -> str:
    if not isinstance(topic, dict):
        return ""
    seo = topic.get("seo", {})
    if isinstance(seo, dict):
        keyword = _clean_text(seo.get("primary_keyword"))
        if keyword:
            return keyword
    return _clean_text(topic.get("topic"))


def normalize_search_intent(value: Any) -> str:
    tokens = []
    for token in _ascii_text(value).split():
        if token in INTENT_STOPWORDS:
            continue
        token = INTENT_TOKEN_ALIASES.get(token, token)
        if token not in tokens:
            tokens.append(token)
    return " ".join(tokens)


def classify_evergreen_intent(topic: Dict[str, Any]) -> Dict[str, Any]:
    keyword = _primary_keyword(topic)
    normalized = _ascii_text(keyword)
    topic_text = _ascii_text(topic.get("topic", "") if isinstance(topic, dict) else "")
    durable = any(pattern in f"{normalized} " for pattern in EVERGREEN_PATTERNS)
    event_only = any(term in topic_text or term in normalized for term in EVENT_ONLY_TERMS)
    eligible = bool(normalized) and (durable or not event_only)
    reason = "durable_search_intent" if eligible else "event_only_or_empty"
    return {
        "eligible": eligible,
        "reason": reason,
        "intent_key": normalize_search_intent(keyword),
    }


def same_search_intent(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    key_a = normalize_search_intent(_primary_keyword(a))
    key_b = normalize_search_intent(_primary_keyword(b))
    if not key_a or not key_b:
        return False
    if key_a == key_b:
        return True
    tokens_a = set(key_a.split())
    tokens_b = set(key_b.split())
    if not tokens_a or not tokens_b:
        return False
    overlap = len(tokens_a & tokens_b)
    shortest = min(len(tokens_a), len(tokens_b))
    return shortest >= 3 and overlap / shortest >= 0.8


def filter_unique_seo_candidates(topics: List[Dict[str, Any]], history: Dict[str, Any]) -> List[Dict[str, Any]]:
    published = history.get("published", []) if isinstance(history, dict) else []
    historical_keys = {
        normalize_search_intent(item.get("intent_key", ""))
        for item in published
        if isinstance(item, dict) and item.get("intent_key")
    }
    output = []
    seen = set()
    for topic in topics if isinstance(topics, list) else []:
        if not isinstance(topic, dict):
            continue
        classification = classify_evergreen_intent(topic)
        if not classification["eligible"]:
            continue
        key = classification["intent_key"]
        if not key or key in historical_keys or key in seen:
            continue
        if any(same_search_intent(topic, existing) for existing in output):
            continue
        seen.add(key)
        output.append(topic)
    return output


def select_seo_candidates(scored_data: Dict[str, Any], max_articles: int = 1, history: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    if not isinstance(scored_data, dict):
        return []
    topics = scored_data.get("topics", [])
    if not isinstance(topics, list):
        return []
    try:
        max_articles = int(max_articles)
    except (TypeError, ValueError):
        max_articles = 1
    if max_articles <= 0:
        return []

    candidates = [
        topic for topic in topics
        if isinstance(topic, dict)
        and _clean_text(topic.get("decision")).upper() == "WRITE"
        and classify_evergreen_intent(topic)["eligible"]
    ]
    candidates.sort(key=lambda item: item.get("total_score", 0), reverse=True)
    candidates = filter_unique_seo_candidates(candidates, history or {"published": []})
    return candidates[:max_articles]


def build_seo_brief(topic: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(topic, dict):
        return {"status": "SEO_BRIEF_BLOCKED", "reason": "Invalid topic."}
    seo = topic.get("seo", {}) if isinstance(topic.get("seo", {}), dict) else {}
    topic_name = _clean_text(topic.get("topic"))
    primary_keyword = _clean_text(seo.get("primary_keyword")) or topic_name
    secondary_keywords = seo.get("secondary_keywords", [])
    if not isinstance(secondary_keywords, list):
        secondary_keywords = []
    secondary_keywords = [_clean_text(item) for item in secondary_keywords if _clean_text(item)]
    search_intent = _clean_text(seo.get("search_intent_type")) or "information"
    suggested_title = _clean_text(seo.get("suggested_title")) or topic_name
    return {
        "status": "SEO_BRIEF_READY",
        "engine_version": SEO_ENGINE_VERSION,
        "topic_id": _clean_text(topic.get("id")),
        "topic": topic_name,
        "score": topic.get("total_score", 0),
        "primary_keyword": primary_keyword,
        "intent_key": normalize_search_intent(primary_keyword),
        "secondary_keywords": secondary_keywords,
        "search_intent": search_intent,
        "recommended_angle": _clean_text(seo.get("recommended_angle")),
        "suggested_title": suggested_title,
        "language": "fr",
        "audience": "joueurs francophones",
        "content_goal": "Créer la meilleure réponse possible à l'intention de recherche.",
        "seo_requirements": {
            "primary_keyword_in_title": True,
            "primary_keyword_in_intro": True,
            "minimum_h2_sections": 2,
            "answer_search_intent": True,
            "include_meta_description": True,
            "natural_keyword_usage": True,
            "avoid_keyword_stuffing": True,
            "include_faq_when_useful": True,
            "suggest_internal_links": True,
        },
        "editorial_requirements": {
            "useful_content": True,
            "original_structure": True,
            "clear_french": True,
            "no_fake_quotes": True,
            "no_invented_precise_facts": True,
            "no_fake_release_dates": True,
            "no_fake_prices": True,
            "no_fake_platform_confirmations": True,
        },
    }


def validate_seo_article(article: Dict[str, Any], brief: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[str] = []
    if not isinstance(article, dict):
        return {"status": "SEO_QUALITY_FAILED", "publishable": False, "issues": ["invalid_article"]}
    if not isinstance(brief, dict):
        return {"status": "SEO_QUALITY_FAILED", "publishable": False, "issues": ["invalid_brief"]}

    title = _clean_text(article.get("title"))
    meta_description = _clean_text(article.get("meta_description"))
    content = _clean_text(article.get("content"))
    primary_keyword = _clean_text(brief.get("primary_keyword"))
    if not title:
        issues.append("title")
    if not meta_description:
        issues.append("meta_description")
    if not content:
        issues.append("content")
    combined_text = " ".join([title, meta_description, content])
    if primary_keyword and not _contains_keyword(combined_text, primary_keyword):
        issues.append("primary_keyword")
    h2_count = len(re.findall(r"<h2(?:\s[^>]*)?>", content, flags=re.IGNORECASE))
    if h2_count < 2:
        issues.append("h2_structure")

    checks = {
        "primary_keyword_found": "primary_keyword" not in issues,
        "h2_count": h2_count,
        "has_title": bool(title),
        "has_meta_description": bool(meta_description),
        "has_content": bool(content),
    }
    if issues:
        return {"status": "SEO_QUALITY_FAILED", "publishable": False, "issues": issues, "checks": checks}
    return {"status": "SEO_QUALITY_PASSED", "publishable": True, "issues": [], "checks": checks}
