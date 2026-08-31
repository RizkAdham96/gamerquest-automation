# =========================================================
# GAMERQUEST TRENDING SEO WRITER V3
# =========================================================

import json
import os
import re

try:
    from groq import Groq
except Exception:
    Groq = None


ALLOWED_STATUS = "CONFIRMED"
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


def _normalize_status(status):
    return str(status or "").strip().upper()


def _normalize_sources(sources):
    if not isinstance(sources, list):
        return []
    output = []
    for source in sources:
        if not isinstance(source, str):
            continue
        source = source.strip()
        if not source or source in output:
            continue
        output.append(source)
    return output


def filter_confirmed_facts(claims):
    if not isinstance(claims, list):
        return []
    confirmed = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if _normalize_status(claim.get("status", "")) != ALLOWED_STATUS:
            continue
        claim_text = str(claim.get("claim", "") or "").strip()
        if not claim_text:
            continue
        sources = _normalize_sources(claim.get("sources", []))
        if not sources:
            continue
        confirmed.append({
            "claim": claim_text,
            "status": "CONFIRMED",
            "sources": sources,
        })
    return confirmed


def _extract_fact_pack(research_record):
    if not isinstance(research_record, dict):
        return {}
    fact_pack = research_record.get("fact_pack", {})
    return fact_pack if isinstance(fact_pack, dict) else {}


def get_confirmed_facts(research_record):
    return filter_confirmed_facts(
        _extract_fact_pack(research_record).get("confirmed_facts", [])
    )


def can_generate_article(research_record):
    return len(get_confirmed_facts(research_record)) > 0


def _safe_string(value):
    return str(value or "").strip()


def _safe_list(value):
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        if not isinstance(item, str):
            continue
        item = item.strip()
        if not item or item in output:
            continue
        output.append(item)
    return output


def _extract_safe_seo_fields(research_record):
    if not isinstance(research_record, dict):
        return {}
    seo = research_record.get("seo", {})
    if not isinstance(seo, dict):
        seo = {}
    return {
        "primary_keyword": _safe_string(seo.get("primary_keyword", "")),
        "secondary_keywords": _safe_list(seo.get("secondary_keywords", [])),
        "search_intent": _safe_string(seo.get("search_intent", "")),
        "suggested_title": _safe_string(seo.get("suggested_title", "")),
    }


def build_writer_input(research_record):
    if not isinstance(research_record, dict):
        return {
            "status": "SKIPPED_NO_CONFIRMED_FACTS",
            "confirmed_facts": [],
        }

    confirmed_facts = get_confirmed_facts(research_record)

    base = {
        "topic_id": _safe_string(research_record.get("id", "")),
        "topic": _safe_string(research_record.get("topic", "")),
        "confirmed_facts": confirmed_facts,
        "seo": _extract_safe_seo_fields(research_record),
    }

    if not confirmed_facts:
        return {"status": "SKIPPED_NO_CONFIRMED_FACTS", **base}

    return {
        "status": "READY_FOR_WRITING",
        **base,
        "writer_rules": {
            "use_only_confirmed_facts": True,
            "invent_facts": False,
            "invent_dates": False,
            "invent_prices": False,
            "invent_platforms": False,
            "invent_quotes": False,
            "invent_features": False,
            "invent_statistics": False,
            "use_blocked_claims": False,
            "publish_directly": False,
        },
    }


def build_writer_prompt(writer_input):
    if not isinstance(writer_input, dict):
        return ""
    if writer_input.get("status") != "READY_FOR_WRITING":
        return ""

    facts = filter_confirmed_facts(writer_input.get("confirmed_facts", []))
    if not facts:
        return ""

    topic = _safe_string(writer_input.get("topic", ""))
    seo = writer_input.get("seo", {})
    if not isinstance(seo, dict):
        seo = {}

    lines = [
        "You are writing a French SEO draft for GamerQuest FR.",
        "",
        "CRITICAL FACT SAFETY RULES:",
        "- Use ONLY the confirmed facts supplied below.",
        "- Never use outside knowledge or memory.",
        "- Never invent or infer missing facts.",
        "- Never invent dates, prices, platforms, quotes, features, statistics, or announcements.",
        "- If information is not in the confirmed facts, do not state it as fact.",
        "- Do not mention blocked or unknown claims.",
        "- This output is a draft only and must be validated before publication.",
        "",
        f"TOPIC: {topic}",
        "",
        "PRIMARY KEYWORD: " + _safe_string(seo.get("primary_keyword", "")),
        "",
        "CONFIRMED FACTS:",
    ]

    for index, fact in enumerate(facts, start=1):
        lines.append(f"{index}. {fact.get('claim', '')}")
        for source in fact.get("sources", []):
            lines.append(f"   SOURCE: {source}")

    lines.extend([
        "",
        "Write a useful French draft based strictly on those confirmed facts.",
        "If there is not enough confirmed information for a useful article, return valid JSON with status SKIPPED_INSUFFICIENT_CONFIRMED_FACTS.",
        "",
        "Return ONLY valid JSON. Do not use Markdown fences.",
        'Required JSON shape: {"title":"","content":"","meta_description":""}',
    ])

    return "\n".join(lines)


def build_generation_request(writer_input):
    if not isinstance(writer_input, dict):
        return {
            "status": "SKIPPED_NO_CONFIRMED_FACTS",
            "should_call_ai": False,
            "prompt": "",
            "confirmed_facts": [],
        }

    if writer_input.get("status") != "READY_FOR_WRITING":
        return {
            "status": writer_input.get("status", "SKIPPED_NO_CONFIRMED_FACTS"),
            "should_call_ai": False,
            "topic": _safe_string(writer_input.get("topic", "")),
            "prompt": "",
            "confirmed_facts": [],
        }

    confirmed_facts = filter_confirmed_facts(
        writer_input.get("confirmed_facts", [])
    )

    if not confirmed_facts:
        return {
            "status": "SKIPPED_NO_CONFIRMED_FACTS",
            "should_call_ai": False,
            "topic": _safe_string(writer_input.get("topic", "")),
            "prompt": "",
            "confirmed_facts": [],
        }

    seo = writer_input.get("seo", {})
    if not isinstance(seo, dict):
        seo = {}

    safe_writer_input = {
        "status": "READY_FOR_WRITING",
        "topic_id": _safe_string(writer_input.get("topic_id", "")),
        "topic": _safe_string(writer_input.get("topic", "")),
        "confirmed_facts": confirmed_facts,
        "seo": {
            "primary_keyword": _safe_string(seo.get("primary_keyword", "")),
            "secondary_keywords": _safe_list(seo.get("secondary_keywords", [])),
            "search_intent": _safe_string(seo.get("search_intent", "")),
            "suggested_title": _safe_string(seo.get("suggested_title", "")),
        },
    }

    prompt = build_writer_prompt(safe_writer_input)

    if not prompt:
        return {
            "status": "SKIPPED_NO_CONFIRMED_FACTS",
            "should_call_ai": False,
            "topic": safe_writer_input["topic"],
            "prompt": "",
            "confirmed_facts": [],
        }

    return {
        "status": "READY_FOR_AI",
        "should_call_ai": True,
        "topic_id": safe_writer_input["topic_id"],
        "topic": safe_writer_input["topic"],
        "confirmed_facts": confirmed_facts,
        "seo": safe_writer_input["seo"],
        "prompt": prompt,
        "publishable": False,
        "published": False,
    }


def normalize_generated_draft(raw_draft):
    if not isinstance(raw_draft, dict):
        raw_draft = {}

    title = _safe_string(raw_draft.get("title", ""))
    content = _safe_string(raw_draft.get("content", ""))
    meta_description = _safe_string(raw_draft.get("meta_description", ""))

    if not title or not content:
        return {
            "status": "BLOCKED_EMPTY_DRAFT",
            "title": title,
            "content": content,
            "meta_description": meta_description,
            "publishable": False,
            "published": False,
        }

    return {
        "status": "DRAFT_PENDING_VALIDATION",
        "title": title,
        "content": content,
        "meta_description": meta_description,
        "publishable": False,
        "published": False,
    }


def _normalize_unsupported_claims(unsupported_claims):
    if not isinstance(unsupported_claims, list):
        return []
    output = []
    for claim in unsupported_claims:
        if isinstance(claim, dict):
            text = _safe_string(claim.get("claim", ""))
        else:
            text = _safe_string(claim)
        if not text or text in output:
            continue
        output.append(text)
    return output


def validate_draft_against_fact_pack(
    draft,
    confirmed_facts,
    unsupported_claims=None,
):
    normalized_draft = normalize_generated_draft(draft)

    if normalized_draft.get("status") == "BLOCKED_EMPTY_DRAFT":
        return {
            "status": "BLOCKED_EMPTY_DRAFT",
            "unsupported_claims": [],
            "publishable": False,
        }

    safe_facts = filter_confirmed_facts(confirmed_facts)

    if not safe_facts:
        return {
            "status": "BLOCKED_NO_CONFIRMED_FACTS",
            "unsupported_claims": [],
            "publishable": False,
        }

    unsupported = _normalize_unsupported_claims(unsupported_claims)

    if unsupported:
        return {
            "status": "BLOCKED_UNSUPPORTED_CLAIMS",
            "unsupported_claims": unsupported,
            "publishable": False,
        }

    return {
        "status": "VALIDATION_PASSED",
        "unsupported_claims": [],
        "confirmed_fact_count": len(safe_facts),
        "publishable": True,
    }


def apply_validation_result(draft, validation):
    normalized_draft = normalize_generated_draft(draft)

    if not isinstance(validation, dict):
        validation = {
            "status": "BLOCKED_VALIDATION_ERROR",
            "unsupported_claims": [],
        }

    validation_status = _safe_string(validation.get("status", ""))

    if validation_status != "VALIDATION_PASSED":
        result = dict(normalized_draft)
        result["status"] = validation_status or "BLOCKED_VALIDATION_ERROR"
        result["unsupported_claims"] = _normalize_unsupported_claims(
            validation.get("unsupported_claims", [])
        )
        result["publishable"] = False
        result["published"] = False
        return result

    if normalized_draft.get("status") == "BLOCKED_EMPTY_DRAFT":
        return normalized_draft

    result = dict(normalized_draft)
    result["status"] = "VALIDATED_DRAFT"
    result["unsupported_claims"] = []
    result["publishable"] = True
    result["published"] = False
    return result


def parse_ai_draft_response(raw):
    if not isinstance(raw, str):
        return {}

    cleaned = raw.strip()
    if not cleaned:
        return {}

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            parsed = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return {}

    if not isinstance(parsed, dict):
        return {}

    status = _safe_string(parsed.get("status", ""))
    if status == "SKIPPED_INSUFFICIENT_CONFIRMED_FACTS":
        return {
            "status": "SKIPPED_INSUFFICIENT_CONFIRMED_FACTS"
        }

    return {
        "title": _safe_string(parsed.get("title", "")),
        "content": _safe_string(parsed.get("content", "")),
        "meta_description": _safe_string(parsed.get("meta_description", "")),
    }


def _build_default_groq_client():
    if not GROQ_API_KEY or Groq is None:
        return None

    try:
        return Groq(
            api_key=GROQ_API_KEY,
            max_retries=0,
        )
    except Exception:
        return None


def generate_draft_with_ai(
    generation_request,
    client=None,
    model=GROQ_MODEL,
):
    if not isinstance(generation_request, dict):
        return {
            "status": "SKIPPED_NO_CONFIRMED_FACTS",
            "publishable": False,
            "published": False,
        }

    request_status = _safe_string(
        generation_request.get("status", "")
    )

    should_call_ai = bool(
        generation_request.get("should_call_ai", False)
    )

    if request_status != "READY_FOR_AI" or not should_call_ai:
        return {
            "status": request_status or "SKIPPED_NO_CONFIRMED_FACTS",
            "publishable": False,
            "published": False,
        }

    prompt = _safe_string(
        generation_request.get("prompt", "")
    )

    if not prompt:
        return {
            "status": "BLOCKED_INVALID_GENERATION_REQUEST",
            "publishable": False,
            "published": False,
        }

    if client is None:
        client = _build_default_groq_client()

    if client is None:
        return {
            "status": "BLOCKED_AI_UNAVAILABLE",
            "publishable": False,
            "published": False,
            "error": (
                "Groq Free client unavailable. "
                "No paid fallback."
            ),
        }

    try:
        response = (
            client
            .chat
            .completions
            .create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the GamerQuest FR SEO draft writer. "
                            "Use only supplied confirmed facts. "
                            "Return JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0,
            )
        )

        raw_content = response.choices[0].message.content

    except Exception as error:
        return {
            "status": "BLOCKED_AI_UNAVAILABLE",
            "publishable": False,
            "published": False,
            "error": f"{type(error).__name__}: {error}",
        }

    parsed = parse_ai_draft_response(raw_content)

    if not parsed:
        return {
            "status": "BLOCKED_INVALID_AI_RESPONSE",
            "publishable": False,
            "published": False,
        }

    if parsed.get("status") == "SKIPPED_INSUFFICIENT_CONFIRMED_FACTS":
        return {
            "status": "SKIPPED_INSUFFICIENT_CONFIRMED_FACTS",
            "publishable": False,
            "published": False,
        }

    normalized = normalize_generated_draft(parsed)

    if normalized.get("status") == "BLOCKED_EMPTY_DRAFT":
        return {
            "status": "BLOCKED_INVALID_AI_RESPONSE",
            "title": normalized.get("title", ""),
            "content": normalized.get("content", ""),
            "meta_description": normalized.get("meta_description", ""),
            "publishable": False,
            "published": False,
        }

    normalized["publishable"] = False
    normalized["published"] = False
    return normalized


def build_skipped_result(research_record):
    writer_input = build_writer_input(research_record)

    if writer_input.get("status") == "READY_FOR_WRITING":
        return None

    return {
        "topic_id": writer_input.get("topic_id", ""),
        "topic": writer_input.get("topic", ""),
        "writer_status": "SKIPPED_NO_CONFIRMED_FACTS",
        "article": None,
        "publishable": False,
        "published": False,
    }


def prepare_article(research_record):
    if not can_generate_article(research_record):
        return build_skipped_result(research_record)

    writer_input = build_writer_input(research_record)
    generation_request = build_generation_request(writer_input)

    return {
        "topic_id": writer_input.get("topic_id", ""),
        "topic": writer_input.get("topic", ""),
        "writer_status": generation_request.get(
            "status",
            "SKIPPED_NO_CONFIRMED_FACTS",
        ),
        "writer_input": writer_input,
        "generation_request": generation_request,
        "article": None,
        "publishable": False,
        "published": False,
    }
