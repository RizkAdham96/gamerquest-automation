import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from groq import Groq, RateLimitError

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from groq_budget import GroqBudgetExhausted, consume_run_budget

BASE_DIR = Path(__file__).resolve().parent
INTEL_FILE = BASE_DIR / "intel" / "topics.json"
SCORED_FILE = BASE_DIR / "scored_topics.json"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "openai/gpt-oss-120b"
MAX_TOPICS_PER_RUN = 8
GROQ_MAX_RETRIES = 3
GROQ_DEFAULT_WAIT_SECONDS = 10

SCORE_LIMITS = {
    "durability": 25,
    "search_intent": 25,
    "long_tail_specificity": 15,
    "french_relevance": 10,
    "competition": 10,
    "gamerquest_relevance": 10,
    "internal_link_potential": 5,
}

GROQ_CLIENT = Groq(api_key=GROQ_API_KEY, max_retries=0) if GROQ_API_KEY else None


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def calculate_total_score(scores):
    total = 0
    for criterion, maximum in SCORE_LIMITS.items():
        value = scores.get(criterion, 0)
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 0
        total += max(0, min(value, maximum))
    return total


def get_decision(total_score):
    if total_score >= 80:
        return "WRITE"
    if total_score >= 65:
        return "REVIEW"
    return "REJECT"


def extract_json(text):
    if not text:
        raise ValueError("Empty AI response.")
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON object found in AI response.")
        return json.loads(cleaned[start:end + 1])


def validate_scores(raw_scores):
    validated = {}
    for criterion, maximum in SCORE_LIMITS.items():
        value = raw_scores.get(criterion, 0)
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 0
        validated[criterion] = max(0, min(value, maximum))
    return validated


def groq_chat(messages):
    if GROQ_CLIENT is None:
        raise RuntimeError("GROQ_API_KEY is missing.")
    consume_run_budget(
        messages,
        650,
        lane="seo",
        operation="seo:manual-scorer",
    )
    for attempt in range(1, GROQ_MAX_RETRIES + 1):
        try:
            response = GROQ_CLIENT.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=650,
            )
            return response.choices[0].message.content
        except RateLimitError as error:
            retry_after = None
            try:
                retry_after = error.response.headers.get("retry-after")
            except Exception:
                pass
            try:
                wait_seconds = float(retry_after)
            except Exception:
                wait_seconds = GROQ_DEFAULT_WAIT_SECONDS * attempt
            wait_seconds += 2
            print(f"Groq free limit: attempt {attempt}/{GROQ_MAX_RETRIES}; waiting {wait_seconds:.1f}s")
            if attempt >= GROQ_MAX_RETRIES:
                raise
            time.sleep(wait_seconds)
    raise RuntimeError("Groq request failed.")


def build_messages(topic):
    system_prompt = """
You are the SEO opportunity analyst for GamerQuest FR, a French-language gaming editorial website.
Your job is NOT to write an article. Evaluate whether a topic deserves a dedicated evergreen SEO resource.

Score using these exact maximum values:
durability: 0-25
search_intent: 0-25
long_tail_specificity: 0-15
french_relevance: 0-10
competition: 0-10
gamerquest_relevance: 0-10
internal_link_potential: 0-5

Reward durable informational or commercial-investigation search intent.
Reward specific French long-tail queries a new domain can realistically rank for.
Reward topics that can naturally link to GamerQuest news, guides, game pages or deals.
Penalize generic breaking news, broad head terms, stale event-only topics, thin topics, and topics whose value depends only on recency.
Do not reward recency by itself.

COMPETITION: low SEO competition = high score; high competition = low score.
Do not invent search volume, traffic, engagement, or facts. Evaluate only evidence contained in the Intel.

Identify primary_keyword, secondary_keywords, search_intent_type, recommended_angle, suggested_title, reasoning.
The suggested title must be natural French and answer a real Google search intent.
Do NOT calculate the final total score; Python calculates it.
Return ONLY valid JSON in this shape:
{
  "scores": {
    "durability": 0,
    "search_intent": 0,
    "long_tail_specificity": 0,
    "french_relevance": 0,
    "competition": 0,
    "gamerquest_relevance": 0,
    "internal_link_potential": 0
  },
  "primary_keyword": "",
  "secondary_keywords": [],
  "search_intent_type": "",
  "recommended_angle": "",
  "suggested_title": "",
  "reasoning": ""
}
""".strip()
    user_prompt = "Analyse this GamerQuest Intel entry:\n\n" + json.dumps(topic, ensure_ascii=False, indent=2)
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]


def analyze_topic_locally(topic):
    """Score SEO opportunities without consuming the shared Groq quota.

    The Intel collector already supplies topic, keywords, source provenance and
    region. Production scoring should be deterministic so the scarce AI budget
    is reserved for the final researched article.
    """
    print("\n===================================")
    print("ANALYSING EVERGREEN SEO TOPIC (LOCAL)")
    print("===================================")
    print(topic.get("topic", "Unknown topic"))

    topic_text = str(topic.get("topic", "") or "").strip()
    normalized = topic_text.lower()
    words = re.findall(r"[a-z0-9à-ÿ]+", normalized)
    keywords = [
        str(item).strip()
        for item in (topic.get("keywords") or [])
        if str(item).strip()
    ]
    sources = [
        item
        for item in (topic.get("sources") or [])
        if isinstance(item, dict)
    ]
    source_types = {
        str(item.get("type", "")).strip().lower()
        for item in sources
    }

    topic_id = str(topic.get("id", "") or "")
    is_feed_lead = topic_id.startswith("rss-")
    has_official = "official" in source_types
    intent_markers = (
        "date de sortie", "plateforme", "platform", "guide", "comment",
        "performance", "patch", "erreur", "error", "crossplay",
        "multijoueur", "multiplayer", "prix", "dlc", "gratuit", "free",
    )
    explicit_intent = any(marker in normalized for marker in intent_markers)

    # Curated/official Intel is durable enough for an evergreen resource.
    # Raw publisher-feed headlines remain leads until a specific search intent
    # is established, so they should not consume article-generation tokens.
    durability = 24 if has_official else 20 if not is_feed_lead else 10
    search_intent = 24 if explicit_intent else 21 if has_official else 12

    word_count = len(words)
    if 3 <= word_count <= 10:
        specificity = 14
    elif 11 <= word_count <= 18:
        specificity = 10
    else:
        specificity = 6

    french_relevance = 10 if str(topic.get("region", "")).upper() == "FR" else 7
    competition = 9 if specificity >= 12 else 6 if specificity >= 9 else 3
    gamerquest_relevance = 10 if sources else 7
    internal_link_potential = 5 if keywords or sources else 3

    scores = validate_scores({
        "durability": durability,
        "search_intent": search_intent,
        "long_tail_specificity": specificity,
        "french_relevance": french_relevance,
        "competition": competition,
        "gamerquest_relevance": gamerquest_relevance,
        "internal_link_potential": internal_link_potential,
    })
    total_score = calculate_total_score(scores)
    decision = get_decision(total_score)

    primary_keyword = keywords[0] if keywords else topic_text
    secondary_keywords = [
        item for item in keywords[1:6]
        if item.lower() != primary_keyword.lower()
    ]

    result = {
        "id": topic.get("id"),
        "topic": topic.get("topic"),
        "detected_at": topic.get("detected_at"),
        "analysed_at": datetime.now(timezone.utc).isoformat(),
        "scores": scores,
        "total_score": total_score,
        "decision": decision,
        "sources": sources,
        "seo": {
            "primary_keyword": primary_keyword,
            "secondary_keywords": secondary_keywords,
            "search_intent_type": "information",
            "recommended_angle": (
                "Réponse evergreen fondée sur les sources vérifiées"
                if decision == "WRITE"
                else "Conserver comme piste jusqu'à un angle de recherche plus précis"
            ),
            "suggested_title": topic_text,
        },
        "reasoning": (
            "Deterministic production score; AI quota is reserved for "
            "research-backed article writing."
        ),
    }
    print(f"Score: {total_score}/100")
    print(f"Decision: {decision}")
    return result


def analyze_topic(topic):
    print("\n===================================")
    print("ANALYSING EVERGREEN SEO TOPIC")
    print("===================================")
    print(topic.get("topic", "Unknown topic"))
    ai_result = extract_json(groq_chat(build_messages(topic)))
    scores = validate_scores(ai_result.get("scores", {}))
    total_score = calculate_total_score(scores)
    decision = get_decision(total_score)
    result = {
        "id": topic.get("id"),
        "topic": topic.get("topic"),
        "detected_at": topic.get("detected_at"),
        "analysed_at": datetime.now(timezone.utc).isoformat(),
        "scores": scores,
        "total_score": total_score,
        "decision": decision,
        "sources": topic.get("sources", []),
        "seo": {
            "primary_keyword": ai_result.get("primary_keyword", ""),
            "secondary_keywords": ai_result.get("secondary_keywords", []),
            "search_intent_type": ai_result.get("search_intent_type", ""),
            "recommended_angle": ai_result.get("recommended_angle", ""),
            "suggested_title": ai_result.get("suggested_title", ""),
        },
        "reasoning": ai_result.get("reasoning", ""),
    }
    print(f"Score: {total_score}/100")
    print(f"Decision: {decision}")
    return result


def get_already_scored_ids(scored_data):
    return {
        topic.get("id")
        for topic in scored_data.get("topics", [])
        if isinstance(topic, dict) and topic.get("id")
    }


def main():
    print("\n===================================")
    print("GAMERQUEST EVERGREEN SEO SCORER")
    print("===================================")
    if not INTEL_FILE.exists():
        print("Intel file not found:", INTEL_FILE)
        sys.exit(1)
    if not SCORED_FILE.exists():
        print("Scored topics file not found:", SCORED_FILE)
        sys.exit(1)
    intel_data = load_json(INTEL_FILE)
    scored_data = load_json(SCORED_FILE)
    already_scored = get_already_scored_ids(scored_data)
    candidates = []
    for topic in intel_data.get("topics", []):
        if not isinstance(topic, dict):
            continue
        topic_id = topic.get("id")
        status = str(topic.get("status", "new")).lower()
        if topic_id and topic_id not in already_scored and status == "new":
            candidates.append(topic)
    candidates = candidates[:MAX_TOPICS_PER_RUN]
    if not candidates:
        print("No new Intel topics to analyse.")
        return
    successful_results = []
    for topic in candidates:
        try:
            successful_results.append(analyze_topic_locally(topic))
        except GroqBudgetExhausted as error:
            print(
                "Shared Groq ceiling reached. Scoring stops safely: "
                f"{error}"
            )
            break
        except RateLimitError:
            print("Groq free limit unavailable. Stopping safely; no paid fallback.")
            break
        except Exception as error:
            print("Topic analysis failed:", str(error))
    if successful_results:
        scored_data.setdefault("topics", []).extend(successful_results)
        scored_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_json(SCORED_FILE, scored_data)
        print(f"Saved {len(successful_results)} new scored topic(s).")
    else:
        print("No new scores were saved.")


if __name__ == "__main__":
    main()
