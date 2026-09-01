# =========================================================
# GAMERQUEST TRENDING SEO — SEO-FIRST PIPELINE V2
# INDEPENDENT SEO AUTOMATION
# WORDPRESS DRAFT ONLY
# =========================================================

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests
from groq import Groq

import scorer

from seo_engine import (
    select_seo_candidates,
    build_seo_brief,
    validate_seo_article,
)


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

SCORED_TOPICS_FILE = (
    BASE_DIR
    / "scored_topics.json"
)

PIPELINE_RESULT_FILE = (
    BASE_DIR
    / "pipeline_result.json"
)


# =========================================================
# CONFIG
# =========================================================

PIPELINE_VERSION = "2.0"

MODEL = "openai/gpt-oss-120b"

# =========================================================
# IMPORTANT:
# This SEO automation is intentionally limited to
# ONE article per run.
# =========================================================

MAX_ARTICLES_PER_RUN = 1

# =========================================================
# SAFE FIRST PRODUCTION TEST:
# WORDPRESS AUTO-PUBLISH.
#
# We will only enable public publishing after this
# independent SEO pipeline passes its real smoke test.
# =========================================================

WORDPRESS_STATUS = "publish"


# =========================================================
# BASIC HELPERS
# =========================================================

def safe_string(value: Any) -> str:
    return str(
        value or ""
    ).strip()


def utc_now() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def load_json(
    path: Path,
) -> Dict[str, Any]:

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        data = json.load(file)

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "JSON root must be an object."
        )

    return data


def save_json(
    path: Path,
    data: Dict[str, Any],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write("\n")


def stop_result(
    status: str,
    reason: str,
    topic: str | None = None,
) -> Dict[str, Any]:

    result = {
        "pipeline_version": (
            PIPELINE_VERSION
        ),
        "status": status,
        "reason": reason,
        "topic": topic,
        "wordpress_status": None,
        "wordpress_post_id": None,
        "wordpress_url": None,
        "published": False,
        "created_at": utc_now(),
    }

    save_json(
        PIPELINE_RESULT_FILE,
        result,
    )

    print("")
    print("=" * 60)
    print("SEO PIPELINE STOPPED")
    print("=" * 60)
    print("STATUS:", status)
    print("REASON:", reason)

    if topic:
        print("TOPIC:", topic)

    print("=" * 60)

    return result


# =========================================================
# WORDPRESS CONFIG
# =========================================================

def get_wordpress_config() -> Dict[str, str]:

    wp_url = safe_string(
        os.environ.get(
            "WP_URL",
            "",
        )
    ).rstrip("/")

    username = safe_string(
        os.environ.get(
            "WP_USERNAME",
            "",
        )
    )

    password = safe_string(
        os.environ.get(
            "WP_APP_PASSWORD",
            "",
        )
    )

    if (
        not wp_url
        or not username
        or not password
    ):
        return {}

    if not (
        wp_url.startswith(
            "https://"
        )
        or wp_url.startswith(
            "http://"
        )
    ):
        return {}

    return {
        "base_url": wp_url,
        "username": username,
        "application_password": (
            password
        ),
    }


# =========================================================
# GROQ RESPONSE HELPERS
# =========================================================

def extract_json_object(
    text: str,
) -> Dict[str, Any]:

    cleaned = safe_string(
        text
    )

    if cleaned.startswith(
        "```"
    ):
        cleaned = cleaned.replace(
            "```json",
            "",
            1,
        )

        cleaned = cleaned.replace(
            "```",
            "",
        )

        cleaned = cleaned.strip()

    try:
        data = json.loads(
            cleaned
        )

        if isinstance(
            data,
            dict,
        ):
            return data

    except Exception:
        pass

    start = cleaned.find(
        "{"
    )

    end = cleaned.rfind(
        "}"
    )

    if (
        start == -1
        or end == -1
        or end <= start
    ):
        raise ValueError(
            "Groq response does not "
            "contain a JSON object."
        )

    candidate = cleaned[
        start:end + 1
    ]

    data = json.loads(
        candidate
    )

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Groq JSON response must "
            "be an object."
        )

    return data


# =========================================================
# SEO WRITING PROMPT
# =========================================================

def build_article_prompt(
    brief: Dict[str, Any],
) -> str:

    topic = safe_string(
        brief.get(
            "topic"
        )
    )

    primary_keyword = safe_string(
        brief.get(
            "primary_keyword"
        )
    )

    secondary_keywords = (
        brief.get(
            "secondary_keywords",
            [],
        )
    )

    search_intent = safe_string(
        brief.get(
            "search_intent"
        )
    )

    recommended_angle = safe_string(
        brief.get(
            "recommended_angle"
        )
    )

    suggested_title = safe_string(
        brief.get(
            "suggested_title"
        )
    )

    secondary_text = ", ".join(
        safe_string(keyword)
        for keyword
        in secondary_keywords
        if safe_string(keyword)
    )

    return f"""
Tu es le rédacteur SEO senior de GamerQuest FR,
un média gaming français.

Ta mission est de créer un article SEO réellement utile
pour les joueurs francophones.

SUJET :
{topic}

MOT-CLÉ PRINCIPAL :
{primary_keyword}

MOTS-CLÉS SECONDAIRES :
{secondary_text}

INTENTION DE RECHERCHE :
{search_intent}

ANGLE RECOMMANDÉ :
{recommended_angle}

TITRE SEO SUGGÉRÉ :
{suggested_title}

OBJECTIF PRINCIPAL :

Répondre mieux que possible à l'intention de recherche
du joueur.

L'article ne doit PAS être une simple actualité courte.

Il doit être construit comme une ressource SEO durable,
claire, structurée et utile.

RÈGLES SEO :

1. Écris en français naturel.

2. Utilise le mot-clé principal naturellement dans :
   - le titre ;
   - l'introduction ;
   - le corps de l'article.

3. Utilise les mots-clés secondaires seulement
   lorsqu'ils sont pertinents.

4. Ne fais jamais de keyword stuffing.

5. Commence l'article par une réponse claire au sujet.

6. Structure le contenu avec plusieurs sections H2.

7. Utilise des H3 lorsque cela améliore la compréhension.

8. Ajoute une section FAQ lorsque le sujet s'y prête.

9. Fais des paragraphes relativement courts.

10. L'article doit répondre concrètement aux questions
    qu'un joueur taperait sur Google.

11. Crée une meta description utile et naturelle.

12. La meta description doit idéalement rester
    autour de 140 à 160 caractères.

13. Ne mets PAS de H1 dans le contenu HTML.
    WordPress utilisera le titre comme H1.

14. Utilise uniquement du HTML simple dans "content" :
    <p>, <h2>, <h3>, <ul>, <ol>, <li>, <strong>.

15. Ne mets aucun Markdown dans le contenu.

RÈGLES DE FIABILITÉ :

Tu peux créer :
- des explications ;
- des guides ;
- des conseils ;
- des comparaisons ;
- des réponses à des questions ;
- du contexte gaming général.

Mais tu ne dois PAS inventer des informations précises.

En particulier :

- aucune fausse date de sortie ;
- aucun faux prix ;
- aucune plateforme présentée comme confirmée
  sans certitude ;
- aucune citation inventée ;
- aucun chiffre précis inventé ;
- aucune annonce officielle inventée ;
- aucune fonctionnalité présentée comme confirmée
  si elle ne l'est pas.

Si une information précise n'est pas certaine,
formule la section sans présenter cette information
comme un fait confirmé.

IMPORTANT :

Le brief peut contenir des hypothèses, angles,
mots-clés ou formulations automatiques.

Ils servent à comprendre l'intention SEO.

Ils ne constituent PAS automatiquement des faits.

FORMAT DE SORTIE OBLIGATOIRE :

Retourne uniquement un objet JSON valide.

Aucun texte avant.
Aucun texte après.
Aucun bloc Markdown.

Structure exacte :

{{
  "title": "Titre SEO",
  "meta_description": "Meta description",
  "content": "<p>Introduction...</p><h2>...</h2>...",
  "primary_keyword": "{primary_keyword}",
  "search_intent": "{search_intent}"
}}
""".strip()


# =========================================================
# GROQ ARTICLE GENERATION
# =========================================================

def generate_seo_article(
    brief: Dict[str, Any],
) -> Dict[str, Any]:

    api_key = safe_string(
        os.environ.get(
            "GROQ_API_KEY",
            "",
        )
    )

    if not api_key:
        return {
            "status": (
                "BLOCKED_MISSING_GROQ_KEY"
            ),
        }

    prompt = build_article_prompt(
        brief
    )

    try:
        client = Groq(
            api_key=api_key
        )

        response = (
            client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Tu es un rédacteur SEO "
                            "gaming français. "
                            "Retourne uniquement "
                            "du JSON valide."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.4,
                max_tokens=5000,
            )
        )

        text = (
            response
            .choices[0]
            .message
            .content
        )

        article = (
            extract_json_object(
                text
            )
        )

    except Exception as error:

        return {
            "status": (
                "BLOCKED_AI_UNAVAILABLE"
            ),
            "error": (
                f"{type(error).__name__}: "
                f"{error}"
            ),
        }

    title = safe_string(
        article.get(
            "title"
        )
    )

    meta_description = safe_string(
        article.get(
            "meta_description"
        )
    )

    content = safe_string(
        article.get(
            "content"
        )
    )

    if (
        not title
        or not meta_description
        or not content
    ):
        return {
            "status": (
                "BLOCKED_INVALID_AI_RESPONSE"
            ),
        }

    return {
        "status": (
            "SEO_ARTICLE_GENERATED"
        ),
        "title": title,
        "meta_description": (
            meta_description
        ),
        "content": content,
        "primary_keyword": (
            safe_string(
                brief.get(
                    "primary_keyword"
                )
            )
        ),
        "search_intent": (
            safe_string(
                brief.get(
                    "search_intent"
                )
            )
        ),
        "publishable": False,
    }


# =========================================================
# LIGHTWEIGHT HIGH-RISK SANITY CHECK
# =========================================================

def high_risk_sanity_check(
    article: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Lightweight guard against obvious unsupported
    high-risk specifics.

    IMPORTANT:
    This is NOT the old Researcher confirmed-facts gate.

    It does not require confirmed_facts.

    It simply prevents obviously dangerous automation
    patterns from passing silently.
    """

    content = safe_string(
        article.get(
            "content"
        )
    )

    lowered = content.lower()

    suspicious_phrases = [
        "date de sortie confirmée",
        "date officielle confirmée",
        "prix officiel confirmé",
        "cd projekt red a confirmé que",
        "le développeur a confirmé que",
        "l'éditeur a confirmé que",
    ]

    found = [
        phrase
        for phrase
        in suspicious_phrases
        if phrase in lowered
    ]

    if found:
        return {
            "status": (
                "SANITY_CHECK_FAILED"
            ),
            "passed": False,
            "issues": found,
        }

    return {
        "status": (
            "SANITY_CHECK_PASSED"
        ),
        "passed": True,
        "issues": [],
    }


# =========================================================
# WORDPRESS DRAFT BRIDGE
# =========================================================

def create_wordpress_draft(
    article: Dict[str, Any],
    wp_config: Dict[str, str],
) -> Dict[str, Any]:

    if not isinstance(
        article,
        dict,
    ):
        return {
            "status": (
                "BLOCKED_INVALID_ARTICLE"
            ),
            "published": False,
        }

    if (
        article.get(
            "publishable"
        )
        is not True
    ):
        return {
            "status": (
                "BLOCKED_NOT_PUBLISHABLE"
            ),
            "published": False,
        }

    base_url = safe_string(
        wp_config.get(
            "base_url"
        )
    ).rstrip("/")

    username = safe_string(
        wp_config.get(
            "username"
        )
    )

    password = safe_string(
        wp_config.get(
            "application_password"
        )
    )

    if (
        not base_url
        or not username
        or not password
    ):
        return {
            "status": (
                "BLOCKED_WORDPRESS_CONFIG"
            ),
            "published": False,
        }

    title = safe_string(
        article.get(
            "title"
        )
    )

    content = safe_string(
        article.get(
            "content"
        )
    )

    meta_description = safe_string(
        article.get(
            "meta_description"
        )
    )

    if (
        not title
        or not content
    ):
        return {
            "status": (
                "BLOCKED_EMPTY_ARTICLE"
            ),
            "published": False,
        }

    endpoint = (
        base_url
        + "/wp-json/wp/v2/posts"
    )

    # =====================================================
    # HARD LOCK:
    # This V2 smoke-test pipeline creates DRAFTS ONLY.
    # =====================================================

    payload = {
        "title": title,
        "content": content,
        "status": WORDPRESS_STATUS,
    }

    if meta_description:
        payload["excerpt"] = (
            meta_description
        )

    try:
        response = requests.post(
            endpoint,
            json=payload,
            auth=(
                username,
                password,
            ),
            timeout=30,
            headers={
                "Accept": (
                    "application/json"
                ),
                "User-Agent": (
                    "GamerQuest-Trending-SEO/"
                    + PIPELINE_VERSION
                ),
            },
        )

    except Exception as error:

        return {
            "status": (
                "BLOCKED_WORDPRESS_UNAVAILABLE"
            ),
            "published": False,
            "error": (
                f"{type(error).__name__}: "
                f"{error}"
            ),
        }

    if not (
        200
        <= response.status_code
        < 300
    ):
        return {
            "status": (
                "BLOCKED_WORDPRESS_ERROR"
            ),
            "published": False,
            "http_status": (
                response.status_code
            ),
        }

    try:
        data = response.json()

    except Exception:

        return {
            "status": (
                "BLOCKED_INVALID_WORDPRESS_RESPONSE"
            ),
            "published": False,
        }

    if not isinstance(
        data,
        dict,
    ):
        return {
            "status": (
                "BLOCKED_INVALID_WORDPRESS_RESPONSE"
            ),
            "published": False,
        }

    post_id = data.get(
        "id"
    )

    wordpress_status = (
        safe_string(
            data.get(
                "status"
            )
        )
        .lower()
    )

    if not post_id:
        return {
            "status": (
                "BLOCKED_INVALID_WORDPRESS_RESPONSE"
            ),
            "published": False,
        }

    if (
        wordpress_status
        != WORDPRESS_STATUS
    ):
        return {
            "status": (
                "BLOCKED_WORDPRESS_STATUS_MISMATCH"
            ),
            "published": False,
            "wordpress_post_id": (
                post_id
            ),
            "wordpress_status": (
                wordpress_status
            ),
        }

    return {
        "status": (
            "WORDPRESS_DRAFT_CREATED"
        ),
        "published": False,
        "wordpress_status": (
            wordpress_status
        ),
        "wordpress_post_id": (
            post_id
        ),
        "wordpress_url": (
            safe_string(
                data.get(
                    "link"
                )
            )
        ),
    }


# =========================================================
# PROCESS ONE SEO TOPIC
# =========================================================

def process_seo_topic(
    topic: Dict[str, Any],
    wp_config: Dict[str, str],
) -> Dict[str, Any]:

    topic_name = safe_string(
        topic.get(
            "topic"
        )
    )

    print("")
    print("=" * 60)
    print("PROCESSING SEO OPPORTUNITY")
    print("=" * 60)
    print("Topic:", topic_name)
    print(
        "Score:",
        topic.get(
            "total_score"
        ),
    )

    # =====================================================
    # STAGE 2 — SEO BRIEF
    # =====================================================

    brief = build_seo_brief(
        topic
    )

    if (
        brief.get(
            "status"
        )
        != "SEO_BRIEF_READY"
    ):
        return stop_result(
            status=(
                "BLOCKED_SEO_BRIEF"
            ),
            reason=(
                "SEO engine could not "
                "create a writing brief."
            ),
            topic=topic_name,
        )

    print("")
    print(
        "Primary keyword:",
        brief.get(
            "primary_keyword"
        ),
    )

    print(
        "Search intent:",
        brief.get(
            "search_intent"
        ),
    )

    # =====================================================
    # STAGE 3 — AI SEO ARTICLE
    # =====================================================

    print("")
    print(
        "Generating SEO article "
        "with Groq..."
    )

    article = generate_seo_article(
        brief
    )

    if (
        article.get(
            "status"
        )
        != "SEO_ARTICLE_GENERATED"
    ):
        return stop_result(
            status=(
                article.get(
                    "status",
                    "BLOCKED_AI_GENERATION",
                )
            ),
            reason=(
                article.get(
                    "error",
                    "Groq did not return "
                    "a valid SEO article.",
                )
            ),
            topic=topic_name,
        )

    print(
        "SEO article generated."
    )

    # =====================================================
    # STAGE 4 — SEO QUALITY CHECK
    # =====================================================

    quality = validate_seo_article(
        article=article,
        brief=brief,
    )

    print("")
    print(
        "SEO quality:",
        quality.get(
            "status"
        ),
    )

    if (
        quality.get(
            "publishable"
        )
        is not True
    ):
        return stop_result(
            status=(
                "SEO_QUALITY_FAILED"
            ),
            reason=(
                "SEO quality issues: "
                + ", ".join(
                    quality.get(
                        "issues",
                        [],
                    )
                )
            ),
            topic=topic_name,
        )

    # =====================================================
    # STAGE 5 — LIGHTWEIGHT SANITY CHECK
    # =====================================================

    sanity = (
        high_risk_sanity_check(
            article
        )
    )

    print(
        "Sanity check:",
        sanity.get(
            "status"
        ),
    )

    if (
        sanity.get(
            "passed"
        )
        is not True
    ):
        return stop_result(
            status=(
                "SANITY_CHECK_FAILED"
            ),
            reason=(
                "Potential unsupported "
                "high-risk factual wording: "
                + ", ".join(
                    sanity.get(
                        "issues",
                        [],
                    )
                )
            ),
            topic=topic_name,
        )

    # =====================================================
    # ARTICLE APPROVED FOR WP DRAFT
    # =====================================================

    article[
        "publishable"
    ] = True

    # =====================================================
    # STAGE 6 — WORDPRESS
    # =====================================================

    print("")
    print(
        "Creating WordPress SEO draft..."
    )

    wordpress_result = (
        create_wordpress_draft(
            article=article,
            wp_config=wp_config,
        )
    )

    if (
        wordpress_result.get(
            "status"
        )
        != "WORDPRESS_DRAFT_CREATED"
    ):
        return stop_result(
            status=(
                wordpress_result.get(
                    "status",
                    "BLOCKED_WORDPRESS",
                )
            ),
            reason=(
                wordpress_result.get(
                    "error",
                    "WordPress draft "
                    "creation failed.",
                )
            ),
            topic=topic_name,
        )

    # =====================================================
    # SUCCESS
    # =====================================================

    result = {
        "pipeline_version": (
            PIPELINE_VERSION
        ),
        "status": (
            "SEO_PIPELINE_DRAFT_SUCCESS"
        ),
        "topic": topic_name,
        "topic_id": (
            topic.get(
                "id"
            )
        ),
        "score": (
            topic.get(
                "total_score"
            )
        ),
        "primary_keyword": (
            brief.get(
                "primary_keyword"
            )
        ),
        "secondary_keywords": (
            brief.get(
                "secondary_keywords",
                [],
            )
        ),
        "search_intent": (
            brief.get(
                "search_intent"
            )
        ),
        "title": (
            article.get(
                "title"
            )
        ),
        "meta_description": (
            article.get(
                "meta_description"
            )
        ),
        "seo_quality_status": (
            quality.get(
                "status"
            )
        ),
        "sanity_status": (
            sanity.get(
                "status"
            )
        ),
        "wordpress_status": (
            wordpress_result.get(
                "wordpress_status"
            )
        ),
        "wordpress_post_id": (
            wordpress_result.get(
                "wordpress_post_id"
            )
        ),
        "wordpress_url": (
            wordpress_result.get(
                "wordpress_url"
            )
        ),
        "published": False,
        "created_at": utc_now(),
    }

    save_json(
        PIPELINE_RESULT_FILE,
        result,
    )

    print("")
    print("=" * 60)
    print("SEO PIPELINE SUCCESS")
    print("=" * 60)

    print(
        "Topic:",
        topic_name,
    )

    print(
        "Title:",
        result.get(
            "title"
        ),
    )

    print(
        "Primary keyword:",
        result.get(
            "primary_keyword"
        ),
    )

    print(
        "SEO quality:",
        result.get(
            "seo_quality_status"
        ),
    )

    print(
        "WordPress Post ID:",
        result.get(
            "wordpress_post_id"
        ),
    )

    print(
        "WordPress status:",
        result.get(
            "wordpress_status"
        ),
    )

    print(
        "Publicly published:",
        result.get(
            "published"
        ),
    )

    print("=" * 60)

    return result


# =========================================================
# FULL INDEPENDENT SEO PIPELINE
# =========================================================

def main() -> None:

    print("")
    print("=" * 60)
    print(
        "GAMERQUEST TRENDING SEO"
    )
    print(
        "SEO-FIRST PIPELINE V2"
    )
    print("=" * 60)

    print(
        "AUTOMATION: SEO ONLY"
    )

    print(
        "MAX ARTICLES PER RUN:",
        MAX_ARTICLES_PER_RUN,
    )

    print(
        "WORDPRESS:",
        WORDPRESS_STATUS.upper(),
        "ONLY",
    )

    print(
        "RESEARCHER CONFIRMED-FACT "
        "GATE: DISABLED"
    )

    print(
        "NEWS AUTOMATION: NOT USED"
    )

    print(
        "DEALS AUTOMATION: NOT USED"
    )

    print("=" * 60)

    # =====================================================
    # ENVIRONMENT
    # =====================================================

    if not safe_string(
        os.environ.get(
            "GROQ_API_KEY",
            "",
        )
    ):
        stop_result(
            status=(
                "BLOCKED_MISSING_GROQ_KEY"
            ),
            reason=(
                "GROQ_API_KEY is missing."
            ),
        )

        return

    wp_config = (
        get_wordpress_config()
    )

    if not wp_config:
        stop_result(
            status=(
                "BLOCKED_WORDPRESS_CONFIG"
            ),
            reason=(
                "WordPress credentials "
                "are missing."
            ),
        )

        return

    # =====================================================
    # STAGE 1 — SEO SCORER
    # =====================================================

    print("")
    print("=" * 60)
    print(
        "STAGE 1 — SEO OPPORTUNITY SCORER"
    )
    print("=" * 60)

    try:
        scorer.main()

    except Exception as error:

        stop_result(
            status=(
                "BLOCKED_SCORER_ERROR"
            ),
            reason=(
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )

        return

    # =====================================================
    # LOAD SCORED SEO TOPICS
    # =====================================================

    if not SCORED_TOPICS_FILE.exists():

        stop_result(
            status=(
                "BLOCKED_NO_SCORED_TOPICS"
            ),
            reason=(
                "scored_topics.json "
                "was not created."
            ),
        )

        return

    try:
        scored_data = load_json(
            SCORED_TOPICS_FILE
        )

    except Exception as error:

        stop_result(
            status=(
                "BLOCKED_INVALID_SCORED_TOPICS"
            ),
            reason=(
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )

        return

    # =====================================================
    # SELECT WRITE OPPORTUNITY
    # =====================================================

    candidates = (
        select_seo_candidates(
            scored_data,
            max_articles=(
                MAX_ARTICLES_PER_RUN
            ),
        )
    )

    if not candidates:

        stop_result(
            status=(
                "SEO_STOP_NO_WRITE_OPPORTUNITY"
            ),
            reason=(
                "No SEO topic currently "
                "has decision=WRITE."
            ),
        )

        return

    # =====================================================
    # ONE ARTICLE MAXIMUM
    # =====================================================

    topic = candidates[0]

    process_seo_topic(
        topic=topic,
        wp_config=wp_config,
    )


if __name__ == "__main__":
    main()
