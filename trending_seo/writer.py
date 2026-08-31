# =========================================================
# GAMERQUEST TRENDING SEO WRITER V1
# =========================================================


ALLOWED_STATUS = "CONFIRMED"


# =========================================================
# FACT FILTERING
# =========================================================

def _normalize_status(status):
    return str(
        status
        or ""
    ).strip().upper()


def _normalize_sources(sources):
    if not isinstance(
        sources,
        list,
    ):
        return []

    output = []

    for source in sources:
        if not isinstance(
            source,
            str,
        ):
            continue

        source = source.strip()

        if not source:
            continue

        if source in output:
            continue

        output.append(
            source
        )

    return output


def filter_confirmed_facts(
    claims,
):
    if not isinstance(
        claims,
        list,
    ):
        return []

    confirmed = []

    for claim in claims:
        if not isinstance(
            claim,
            dict,
        ):
            continue

        status = _normalize_status(
            claim.get(
                "status",
                "",
            )
        )

        if status != ALLOWED_STATUS:
            continue

        claim_text = str(
            claim.get(
                "claim",
                "",
            )
            or ""
        ).strip()

        if not claim_text:
            continue

        sources = _normalize_sources(
            claim.get(
                "sources",
                [],
            )
        )

        # Hard safety rule:
        # confirmed facts without source evidence
        # cannot reach the writer.
        if not sources:
            continue

        confirmed.append(
            {
                "claim": claim_text,
                "status": "CONFIRMED",
                "sources": sources,
            }
        )

    return confirmed


# =========================================================
# ARTICLE ELIGIBILITY
# =========================================================

def _extract_fact_pack(
    research_record,
):
    if not isinstance(
        research_record,
        dict,
    ):
        return {}

    fact_pack = research_record.get(
        "fact_pack",
        {},
    )

    if not isinstance(
        fact_pack,
        dict,
    ):
        return {}

    return fact_pack


def get_confirmed_facts(
    research_record,
):
    fact_pack = _extract_fact_pack(
        research_record
    )

    facts = fact_pack.get(
        "confirmed_facts",
        [],
    )

    return filter_confirmed_facts(
        facts
    )


def can_generate_article(
    research_record,
):
    confirmed_facts = (
        get_confirmed_facts(
            research_record
        )
    )

    return len(
        confirmed_facts
    ) > 0


# =========================================================
# SAFE SEO INPUT
# =========================================================

def _safe_string(value):
    return str(
        value
        or ""
    ).strip()


def _safe_list(value):
    if not isinstance(
        value,
        list,
    ):
        return []

    output = []

    for item in value:
        if not isinstance(
            item,
            str,
        ):
            continue

        item = item.strip()

        if not item:
            continue

        if item in output:
            continue

        output.append(
            item
        )

    return output


def _extract_safe_seo_fields(
    research_record,
):
    """
    Only return SEO/navigation fields.

    No factual claims from blocked_claims,
    research notes, raw evidence, or model output
    are included here.
    """

    if not isinstance(
        research_record,
        dict,
    ):
        return {}

    seo = research_record.get(
        "seo",
        {},
    )

    if not isinstance(
        seo,
        dict,
    ):
        seo = {}

    safe_fields = {
        "primary_keyword": _safe_string(
            seo.get(
                "primary_keyword",
                "",
            )
        ),
        "secondary_keywords": _safe_list(
            seo.get(
                "secondary_keywords",
                [],
            )
        ),
        "search_intent": _safe_string(
            seo.get(
                "search_intent",
                "",
            )
        ),
        "suggested_title": _safe_string(
            seo.get(
                "suggested_title",
                "",
            )
        ),
    }

    return safe_fields


# =========================================================
# WRITER INPUT
# =========================================================

def build_writer_input(
    research_record,
):
    if not isinstance(
        research_record,
        dict,
    ):
        return {
            "status": (
                "SKIPPED_NO_CONFIRMED_FACTS"
            ),
            "confirmed_facts": [],
        }

    confirmed_facts = (
        get_confirmed_facts(
            research_record
        )
    )

    if not confirmed_facts:
        return {
            "status": (
                "SKIPPED_NO_CONFIRMED_FACTS"
            ),
            "topic_id": _safe_string(
                research_record.get(
                    "id",
                    "",
                )
            ),
            "topic": _safe_string(
                research_record.get(
                    "topic",
                    "",
                )
            ),
            "confirmed_facts": [],
            "seo": (
                _extract_safe_seo_fields(
                    research_record
                )
            ),
        }

    return {
        "status": (
            "READY_FOR_WRITING"
        ),

        "topic_id": _safe_string(
            research_record.get(
                "id",
                "",
            )
        ),

        "topic": _safe_string(
            research_record.get(
                "topic",
                "",
            )
        ),

        "confirmed_facts": (
            confirmed_facts
        ),

        "seo": (
            _extract_safe_seo_fields(
                research_record
            )
        ),

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


# =========================================================
# PROMPT SAFETY
# =========================================================

def build_writer_prompt(
    writer_input,
):
    """
    This is intentionally deterministic and contains
    only the already-filtered writer input.

    The final AI generation step comes later.
    """

    if not isinstance(
        writer_input,
        dict,
    ):
        return ""

    if (
        writer_input.get(
            "status"
        )
        != "READY_FOR_WRITING"
    ):
        return ""

    facts = writer_input.get(
        "confirmed_facts",
        [],
    )

    if not facts:
        return ""

    topic = _safe_string(
        writer_input.get(
            "topic",
            "",
        )
    )

    seo = writer_input.get(
        "seo",
        {},
    )

    if not isinstance(
        seo,
        dict,
    ):
        seo = {}

    lines = [
        (
            "You are writing a French SEO article "
            "for GamerQuest FR."
        ),
        "",
        (
            "CRITICAL FACT SAFETY RULES:"
        ),
        (
            "- Use ONLY the confirmed facts supplied below."
        ),
        (
            "- Never use outside knowledge or memory."
        ),
        (
            "- Never invent or infer missing facts."
        ),
        (
            "- Never invent dates, prices, platforms, "
            "quotes, features, statistics, or announcements."
        ),
        (
            "- If information is not in the confirmed facts, "
            "do not state it as fact."
        ),
        (
            "- Do not mention blocked or unknown claims."
        ),
        (
            "- Do not publish anything directly."
        ),
        "",
        f"TOPIC: {topic}",
        "",
        (
            "PRIMARY KEYWORD: "
            + _safe_string(
                seo.get(
                    "primary_keyword",
                    "",
                )
            )
        ),
        "",
        "CONFIRMED FACTS:",
    ]

    for index, fact in enumerate(
        facts,
        start=1,
    ):
        lines.append(
            (
                f"{index}. "
                f"{fact.get('claim', '')}"
            )
        )

        sources = fact.get(
            "sources",
            [],
        )

        for source in sources:
            lines.append(
                f"   SOURCE: {source}"
            )

    lines.extend(
        [
            "",
            (
                "Create a clear, useful French article "
                "based strictly on those facts."
            ),
            (
                "If the confirmed fact set is too limited "
                "for a useful article, return:"
            ),
            (
                "SKIPPED_INSUFFICIENT_CONFIRMED_FACTS"
            ),
        ]
    )

    return "\n".join(
        lines
    )


# =========================================================
# DRAFT STATE
# =========================================================

def build_skipped_result(
    research_record,
):
    writer_input = build_writer_input(
        research_record
    )

    if (
        writer_input.get(
            "status"
        )
        == "READY_FOR_WRITING"
    ):
        return None

    return {
        "topic_id": writer_input.get(
            "topic_id",
            "",
        ),
        "topic": writer_input.get(
            "topic",
            "",
        ),
        "writer_status": (
            "SKIPPED_NO_CONFIRMED_FACTS"
        ),
        "article": None,
        "publishable": False,
    }


# =========================================================
# V1 ENTRY POINT
# =========================================================

def prepare_article(
    research_record,
):
    """
    Writer V1 stops at the safe preparation stage.

    Actual Groq article generation and final
    article-vs-fact-pack validation come in the next
    bounded step.
    """

    if not can_generate_article(
        research_record
    ):
        return build_skipped_result(
            research_record
        )

    writer_input = build_writer_input(
        research_record
    )

    prompt = build_writer_prompt(
        writer_input
    )

    return {
        "topic_id": writer_input.get(
            "topic_id",
            "",
        ),
        "topic": writer_input.get(
            "topic",
            "",
        ),
        "writer_status": (
            "READY_FOR_GENERATION"
        ),
        "writer_input": writer_input,
        "prompt": prompt,
        "article": None,
        "publishable": False,
    }
