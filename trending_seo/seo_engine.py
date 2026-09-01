"""
GamerQuest Trending SEO Engine V1

Independent SEO-content engine.

IMPORTANT:
- This module belongs ONLY to the Trending SEO automation.
- It does NOT control the News automation.
- It does NOT control the Deals automation.
- It does NOT require Researcher confirmed_facts.
- Its job is SEO opportunity selection, SEO briefing and SEO quality checks.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


SEO_ENGINE_VERSION = "1.0"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_keyword(value: Any) -> str:
    return " ".join(_clean_text(value).lower().split())


def _contains_keyword(text: str, keyword: str) -> bool:
    text_normalized = _normalize_keyword(text)
    keyword_normalized = _normalize_keyword(keyword)

    if not keyword_normalized:
        return False

    return keyword_normalized in text_normalized


def select_seo_candidates(
    scored_data: Dict[str, Any],
    max_articles: int = 1,
) -> List[Dict[str, Any]]:
    """
    Select SEO opportunities independently from Researcher.

    Only topics explicitly marked WRITE are eligible.

    confirmed_facts and research_status are intentionally NOT required.
    """

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

    candidates = []

    for topic in topics:
        if not isinstance(topic, dict):
            continue

        decision = _clean_text(
            topic.get("decision")
        ).upper()

        if decision != "WRITE":
            continue

        candidates.append(topic)

    candidates.sort(
        key=lambda item: item.get("total_score", 0),
        reverse=True,
    )

    return candidates[:max_articles]


def build_seo_brief(
    topic: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Convert a scored WRITE topic into an SEO writing brief.

    This intentionally does not depend on:
    - confirmed_facts
    - research_status
    - VERIFIED_FACTS_READY
    """

    if not isinstance(topic, dict):
        return {
            "status": "SEO_BRIEF_BLOCKED",
            "reason": "Invalid topic.",
        }

    seo = topic.get("seo", {})

    if not isinstance(seo, dict):
        seo = {}

    topic_name = _clean_text(
        topic.get("topic")
    )

    primary_keyword = _clean_text(
        seo.get("primary_keyword")
    )

    if not primary_keyword:
        primary_keyword = topic_name

    secondary_keywords = seo.get(
        "secondary_keywords",
        [],
    )

    if not isinstance(secondary_keywords, list):
        secondary_keywords = []

    secondary_keywords = [
        _clean_text(keyword)
        for keyword in secondary_keywords
        if _clean_text(keyword)
    ]

    search_intent = _clean_text(
        seo.get("search_intent_type")
    )

    if not search_intent:
        search_intent = "information"

    recommended_angle = _clean_text(
        seo.get("recommended_angle")
    )

    suggested_title = _clean_text(
        seo.get("suggested_title")
    )

    if not suggested_title:
        suggested_title = topic_name

    return {
        "status": "SEO_BRIEF_READY",
        "engine_version": SEO_ENGINE_VERSION,
        "topic_id": _clean_text(
            topic.get("id")
        ),
        "topic": topic_name,
        "score": topic.get("total_score", 0),
        "primary_keyword": primary_keyword,
        "secondary_keywords": secondary_keywords,
        "search_intent": search_intent,
        "recommended_angle": recommended_angle,
        "suggested_title": suggested_title,
        "language": "fr",
        "audience": "joueurs francophones",
        "content_goal": (
            "Créer la meilleure réponse possible "
            "à l'intention de recherche."
        ),
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


def validate_seo_article(
    article: Dict[str, Any],
    brief: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Lightweight deterministic SEO quality gate.

    This is NOT the old confirmed-facts gate.

    It checks whether the generated article is structurally useful
    for SEO before WordPress receives it.
    """

    issues: List[str] = []

    if not isinstance(article, dict):
        return {
            "status": "SEO_QUALITY_FAILED",
            "publishable": False,
            "issues": ["invalid_article"],
        }

    if not isinstance(brief, dict):
        return {
            "status": "SEO_QUALITY_FAILED",
            "publishable": False,
            "issues": ["invalid_brief"],
        }

    title = _clean_text(
        article.get("title")
    )

    meta_description = _clean_text(
        article.get("meta_description")
    )

    content = _clean_text(
        article.get("content")
    )

    primary_keyword = _clean_text(
        brief.get("primary_keyword")
    )

    if not title:
        issues.append("title")

    if not meta_description:
        issues.append("meta_description")

    if not content:
        issues.append("content")

    combined_text = " ".join(
        [
            title,
            meta_description,
            content,
        ]
    )

    if (
        primary_keyword
        and not _contains_keyword(
            combined_text,
            primary_keyword,
        )
    ):
        issues.append("primary_keyword")

    h2_count = len(
        re.findall(
            r"<h2(?:\s[^>]*)?>",
            content,
            flags=re.IGNORECASE,
        )
    )

    if h2_count < 2:
        issues.append("h2_structure")

    if issues:
        return {
            "status": "SEO_QUALITY_FAILED",
            "publishable": False,
            "issues": issues,
            "checks": {
                "primary_keyword_found": (
                    "primary_keyword"
                    not in issues
                ),
                "h2_count": h2_count,
                "has_title": bool(title),
                "has_meta_description": bool(
                    meta_description
                ),
                "has_content": bool(content),
            },
        }

    return {
        "status": "SEO_QUALITY_PASSED",
        "publishable": True,
        "issues": [],
        "checks": {
            "primary_keyword_found": True,
            "h2_count": h2_count,
            "has_title": True,
            "has_meta_description": True,
            "has_content": True,
        },
    }
