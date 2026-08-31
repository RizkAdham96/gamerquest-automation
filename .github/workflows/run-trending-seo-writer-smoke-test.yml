import json

from writer import (
    build_writer_input,
    build_generation_request,
    generate_draft_with_ai,
)


def main():
    research_record = {
        "id": "writer-v3-smoke-test",
        "topic": "Test Game",
        "seo": {
            "primary_keyword": "Test Game",
            "secondary_keywords": [],
            "search_intent": "informational",
            "suggested_title": "Test Game : annonce officielle",
        },
        "fact_pack": {
            "confirmed_facts": [
                {
                    "claim": (
                        "Dans ce scénario de test contrôlé, "
                        "Test Game a été officiellement annoncé."
                    ),
                    "status": "CONFIRMED",
                    "sources": [
                        "https://gamerquestfr.com/"
                    ],
                }
            ],
            "blocked_claims": [],
        },
    }

    writer_input = build_writer_input(
        research_record
    )

    print("=" * 60)
    print("GAMERQUEST WRITER V3 — REAL GROQ SMOKE TEST")
    print("=" * 60)
    print("WRITER INPUT STATUS:", writer_input.get("status"))
    print(
        "CONFIRMED FACTS:",
        len(writer_input.get("confirmed_facts", [])),
    )

    generation_request = build_generation_request(
        writer_input
    )

    print(
        "GENERATION STATUS:",
        generation_request.get("status"),
    )
    print(
        "SHOULD CALL AI:",
        generation_request.get("should_call_ai"),
    )

    if generation_request.get("status") != "READY_FOR_AI":
        raise SystemExit(
            "Writer smoke test blocked before AI generation."
        )

    draft = generate_draft_with_ai(
        generation_request=generation_request
    )

    print(
        "DRAFT STATUS:",
        draft.get("status"),
    )
    print(
        "PUBLISHABLE:",
        draft.get("publishable"),
    )
    print(
        "PUBLISHED:",
        draft.get("published"),
    )

    if draft.get("status") != "DRAFT_PENDING_VALIDATION":
        print("FULL RESULT:")
        print(
            json.dumps(
                draft,
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(
            "Real Groq generation did not return a valid pending draft."
        )

    if draft.get("publishable") is not False:
        raise SystemExit(
            "Safety failure: draft became publishable before validation."
        )

    if draft.get("published") is not False:
        raise SystemExit(
            "Safety failure: draft was marked published."
        )

    print(
        "TITLE:",
        draft.get("title"),
    )
    print(
        "META DESCRIPTION:",
        draft.get("meta_description"),
    )
    print("CONTENT:")
    print(
        draft.get("content")
    )

    print("=" * 60)
    print(
        "REAL GROQ WRITER SMOKE TEST: PASS"
    )
    print(
        "Draft remains blocked from publication pending validation."
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
