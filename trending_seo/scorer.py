import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from groq import Groq, RateLimitError


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

INTEL_FILE = BASE_DIR / "intel" / "topics.json"
SCORED_FILE = BASE_DIR / "scored_topics.json"


# =========================================================
# CONFIGURATION
# =========================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

GROQ_MODEL = "openai/gpt-oss-120b"

# Safety:
# Never analyse unlimited topics in one run.
MAX_TOPICS_PER_RUN = 3

# We handle retries ourselves.
GROQ_MAX_RETRIES = 3
GROQ_DEFAULT_WAIT_SECONDS = 10


# =========================================================
# SCORE LIMITS
# =========================================================

SCORE_LIMITS = {
    "trend_strength": 25,
    "search_intent": 25,
    "freshness": 20,
    "french_relevance": 15,
    "competition": 10,
    "gamerquest_relevance": 5,
}


# =========================================================
# GROQ CLIENT
# =========================================================

if GROQ_API_KEY:
    GROQ_CLIENT = Groq(
        api_key=GROQ_API_KEY,
        max_retries=0,
    )
else:
    GROQ_CLIENT = None


# =========================================================
# BASIC HELPERS
# =========================================================

def load_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def save_json(path, data):
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


# =========================================================
# SCORE CALCULATION
# =========================================================

def calculate_total_score(scores):
    """
    Calculate the final score using Python.

    The AI is NOT trusted to calculate the total.
    """

    total = 0

    for criterion, maximum in SCORE_LIMITS.items():

        value = scores.get(
            criterion,
            0,
        )

        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 0

        value = max(
            0,
            min(
                value,
                maximum,
            ),
        )

        total += value

    return total


def get_decision(total_score):
    """
    Convert score into editorial decision.
    """

    if total_score >= 80:
        return "WRITE"

    if total_score >= 65:
        return "REVIEW"

    return "REJECT"


# =========================================================
# JSON EXTRACTION
# =========================================================

def extract_json(text):
    """
    Groq should return JSON only.

    This function also safely handles responses wrapped
    inside Markdown ```json blocks.
    """

    if not text:
        raise ValueError(
            "Empty AI response."
        )

    cleaned = text.strip()

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    )

    try:
        return json.loads(
            cleaned
        )

    except json.JSONDecodeError:

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start == -1 or end == -1:
            raise ValueError(
                "No JSON object found in AI response."
            )

        return json.loads(
            cleaned[
                start:end + 1
            ]
        )


# =========================================================
# VALIDATION
# =========================================================

def validate_scores(raw_scores):
    """
    Validate and clamp every AI score.

    Example:
    trend_strength cannot exceed 25.
    """

    validated = {}

    for criterion, maximum in SCORE_LIMITS.items():

        value = raw_scores.get(
            criterion,
            0,
        )

        try:
            value = int(value)

        except (TypeError, ValueError):
            value = 0

        validated[criterion] = max(
            0,
            min(
                value,
                maximum,
            ),
        )

    return validated


# =========================================================
# GROQ FREE-TIER SAFE CALL
# =========================================================

def groq_chat(messages):
    """
    Make one Groq request.

    IMPORTANT:
    - No paid fallback.
    - No second provider.
    - Rate limit = wait/retry.
    - If retries fail, stop processing.

    This is designed for the existing Groq free setup.
    """

    if GROQ_CLIENT is None:
        raise RuntimeError(
            "GROQ_API_KEY is missing."
        )

    for attempt in range(
        1,
        GROQ_MAX_RETRIES + 1,
    ):

        try:
            response = (
                GROQ_CLIENT
                .chat
                .completions
                .create(
                    model=GROQ_MODEL,
                    messages=messages,
                    temperature=0.1,
                )
            )

            return (
                response
                .choices[0]
                .message
                .content
            )

        except RateLimitError as error:

            retry_after = None

            try:
                retry_after = (
                    error
                    .response
                    .headers
                    .get(
                        "retry-after"
                    )
                )
            except Exception:
                retry_after = None

            try:
                wait_seconds = float(
                    retry_after
                )
            except Exception:
                wait_seconds = (
                    GROQ_DEFAULT_WAIT_SECONDS
                    * attempt
                )

            wait_seconds += 2

            print("")
            print(
                "==================================="
            )
            print(
                "GROQ FREE LIMIT REACHED"
            )
            print(
                "==================================="
            )

            print(
                f"Attempt "
                f"{attempt}/"
                f"{GROQ_MAX_RETRIES}"
            )

            print(
                f"Waiting "
                f"{wait_seconds:.1f} seconds..."
            )

            if attempt >= GROQ_MAX_RETRIES:
                raise

            time.sleep(
                wait_seconds
            )

    raise RuntimeError(
        "Groq request failed."
    )


# =========================================================
# AI PROMPT
# =========================================================

def build_messages(topic):
    """
    Build the SEO scoring prompt.
    """

    system_prompt = """
You are the SEO opportunity analyst for GamerQuest FR,
a French-language gaming editorial website.

Your job is NOT to write an article.

Your only job is to evaluate whether a gaming topic
deserves a dedicated SEO-focused article.

Score the topic using these exact maximum values:

trend_strength: 0-25
search_intent: 0-25
freshness: 0-20
french_relevance: 0-15
competition: 0-10
gamerquest_relevance: 0-5

IMPORTANT COMPETITION RULE:

competition measures GamerQuest's realistic opportunity.

Low SEO competition = high score.
High SEO competition = low score.

Examples:

Low competition = approximately 8-10
Medium competition = approximately 5-7
High competition = approximately 0-4

Do not invent engagement numbers.

Evaluate only the evidence contained in the Intel.

Identify:

- primary_keyword
- secondary_keywords
- search_intent_type
- recommended_angle
- suggested_title
- reasoning

The suggested title must be natural French and designed
to answer a real Google search intent.

Do NOT calculate the final total score.
Python will calculate it.

Return ONLY valid JSON.

Required format:

{
  "scores": {
    "trend_strength": 0,
    "search_intent": 0,
    "freshness": 0,
    "french_relevance": 0,
    "competition": 0,
    "gamerquest_relevance": 0
  },
  "primary_keyword": "",
  "secondary_keywords": [],
  "search_intent_type": "",
  "recommended_angle": "",
  "suggested_title": "",
  "reasoning": ""
}
""".strip()

    user_prompt = (
        "Analyse this GamerQuest Intel entry:\n\n"
        + json.dumps(
            topic,
            ensure_ascii=False,
            indent=2,
        )
    )

    return [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]


# =========================================================
# ANALYSE ONE TOPIC
# =========================================================

def analyze_topic(topic):

    print("")
    print(
        "==================================="
    )

    print(
        "ANALYSING TRENDING SEO TOPIC"
    )

    print(
        "==================================="
    )

    print(
        topic.get(
            "topic",
            "Unknown topic",
        )
    )

    response_text = groq_chat(
        build_messages(
            topic
        )
    )

    ai_result = extract_json(
        response_text
    )

    raw_scores = ai_result.get(
        "scores",
        {},
    )

    scores = validate_scores(
        raw_scores
    )

    total_score = calculate_total_score(
        scores
    )

    decision = get_decision(
        total_score
    )

    result = {
        "id": topic.get(
            "id"
        ),
        "topic": topic.get(
            "topic"
        ),
        "detected_at": topic.get(
            "detected_at"
        ),
        "analysed_at": (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        ),
        "scores": scores,
        "total_score": total_score,
        "decision": decision,
        "seo": {
            "primary_keyword": (
                ai_result.get(
                    "primary_keyword",
                    ""
                )
            ),
            "secondary_keywords": (
                ai_result.get(
                    "secondary_keywords",
                    []
                )
            ),
            "search_intent_type": (
                ai_result.get(
                    "search_intent_type",
                    ""
                )
            ),
            "recommended_angle": (
                ai_result.get(
                    "recommended_angle",
                    ""
                )
            ),
            "suggested_title": (
                ai_result.get(
                    "suggested_title",
                    ""
                )
            ),
        },
        "reasoning": ai_result.get(
            "reasoning",
            ""
        ),
    }

    print(
        f"Score: "
        f"{total_score}/100"
    )

    print(
        f"Decision: "
        f"{decision}"
    )

    return result


# =========================================================
# DUPLICATE PROTECTION
# =========================================================

def get_already_scored_ids(scored_data):

    ids = set()

    for topic in scored_data.get(
        "topics",
        [],
    ):

        topic_id = topic.get(
            "id"
        )

        if topic_id:
            ids.add(
                topic_id
            )

    return ids


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print(
        "==================================="
    )
    print(
        "GAMERQUEST TRENDING SEO SCORER"
    )
    print(
        "==================================="
    )

    if not INTEL_FILE.exists():

        print(
            "Intel file not found:"
        )

        print(
            INTEL_FILE
        )

        sys.exit(
            1
        )

    if not SCORED_FILE.exists():

        print(
            "Scored topics file not found:"
        )

        print(
            SCORED_FILE
        )

        sys.exit(
            1
        )

    intel_data = load_json(
        INTEL_FILE
    )

    scored_data = load_json(
        SCORED_FILE
    )

    already_scored = (
        get_already_scored_ids(
            scored_data
        )
    )

    candidates = []

    for topic in intel_data.get(
        "topics",
        [],
    ):

        topic_id = topic.get(
            "id"
        )

        status = (
            topic.get(
                "status",
                "new",
            )
            .lower()
        )

        if not topic_id:
            continue

        if topic_id in already_scored:
            continue

        if status != "new":
            continue

        candidates.append(
            topic
        )

    if not candidates:

        print(
            "No new Intel topics to analyse."
        )

        return

    candidates = candidates[
        :MAX_TOPICS_PER_RUN
    ]

    print(
        f"New topics selected: "
        f"{len(candidates)}"
    )

    successful_results = []

    for topic in candidates:

        try:

            result = analyze_topic(
                topic
            )

            successful_results.append(
                result
            )

        except RateLimitError:

            print("")
            print(
                "Groq free limit still unavailable."
            )

            print(
                "Stopping safely."
            )

            print(
                "No paid fallback will be used."
            )

            break

        except Exception as error:

            print("")
            print(
                "Topic analysis failed:"
            )

            print(
                str(error)
            )

            # One broken topic must not destroy
            # previously successful analyses.
            continue

    if successful_results:

        scored_data.setdefault(
            "topics",
            []
        )

        scored_data[
            "topics"
        ].extend(
            successful_results
        )

        scored_data[
            "updated_at"
        ] = (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )

        save_json(
            SCORED_FILE,
            scored_data,
        )

        print("")
        print(
            f"Saved "
            f"{len(successful_results)} "
            f"new scored topic(s)."
        )

    else:

        print("")
        print(
            "No new scores were saved."
        )

    print("")
    print(
        "Trending SEO scoring complete."
    )


if __name__ == "__main__":
    main()
