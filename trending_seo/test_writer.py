import unittest

from writer import (
    # V1
    build_writer_input,
    can_generate_article,
    filter_confirmed_facts,

    # V2
    build_generation_request,
    normalize_generated_draft,
    validate_draft_against_fact_pack,
    apply_validation_result,

    # V3
    parse_ai_draft_response,
    generate_draft_with_ai,
)


class FakeResponse:
    def __init__(self, content):
        class Message:
            pass

        class Choice:
            pass

        message = Message()
        message.content = content

        choice = Choice()
        choice.message = message

        self.choices = [choice]


class FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return FakeResponse(self.content)


class FakeChat:
    def __init__(self, content):
        self.completions = FakeCompletions(
            content
        )


class FakeGroqClient:
    def __init__(self, content):
        self.chat = FakeChat(content)


class ExplodingCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        raise RuntimeError(
            "AI should not have been called"
        )


class ExplodingChat:
    def __init__(self):
        self.completions = (
            ExplodingCompletions()
        )


class ExplodingGroqClient:
    def __init__(self):
        self.chat = ExplodingChat()


class TestTrendingSEOWriter(unittest.TestCase):

    # ======================================================
    # V1 — FACT GATE
    # ======================================================

    def test_zero_confirmed_facts_blocks_writer(self):
        research_record = {
            "fact_pack": {
                "confirmed_facts": [],
                "blocked_claims": [
                    {
                        "claim": "Unverified release date",
                        "status": "UNKNOWN",
                    }
                ],
            }
        }

        self.assertFalse(
            can_generate_article(
                research_record
            )
        )

    def test_writer_allowed_with_confirmed_fact(self):
        research_record = {
            "fact_pack": {
                "confirmed_facts": [
                    {
                        "claim": (
                            "The game was officially "
                            "announced."
                        ),
                        "status": "CONFIRMED",
                        "sources": [
                            "https://example.com/official"
                        ],
                    }
                ],
                "blocked_claims": [],
            }
        }

        self.assertTrue(
            can_generate_article(
                research_record
            )
        )

    def test_filter_removes_unknown_claims(self):
        claims = [
            {
                "claim": "Confirmed announcement.",
                "status": "CONFIRMED",
                "sources": [
                    "https://example.com/official"
                ],
            },
            {
                "claim": "Possible release date.",
                "status": "UNKNOWN",
                "sources": [],
            },
            {
                "claim": "Rumored platform.",
                "status": "UNCONFIRMED",
                "sources": [],
            },
        ]

        result = filter_confirmed_facts(
            claims
        )

        self.assertEqual(
            len(result),
            1,
        )

        self.assertEqual(
            result[0]["claim"],
            "Confirmed announcement.",
        )

    def test_confirmed_fact_requires_source(self):
        claims = [
            {
                "claim": "Claim without evidence.",
                "status": "CONFIRMED",
                "sources": [],
            }
        ]

        self.assertEqual(
            filter_confirmed_facts(claims),
            [],
        )

    def test_writer_input_excludes_blocked_claims(self):
        research_record = {
            "id": "test-topic",
            "topic": "Test Game",
            "fact_pack": {
                "confirmed_facts": [
                    {
                        "claim": (
                            "Official confirmed fact."
                        ),
                        "status": "CONFIRMED",
                        "sources": [
                            "https://example.com/official"
                        ],
                    }
                ],
                "blocked_claims": [
                    {
                        "claim": (
                            "Secret unverified "
                            "release date."
                        ),
                        "status": "UNKNOWN",
                    }
                ],
            },
        }

        result = str(
            build_writer_input(
                research_record
            )
        )

        self.assertIn(
            "Official confirmed fact.",
            result,
        )

        self.assertNotIn(
            "Secret unverified release date.",
            result,
        )

    # ======================================================
    # V2 — GENERATION REQUEST
    # ======================================================

    def test_generation_request_blocked_without_facts(self):
        writer_input = {
            "status": (
                "SKIPPED_NO_CONFIRMED_FACTS"
            ),
            "topic": "Test Game",
            "confirmed_facts": [],
        }

        result = build_generation_request(
            writer_input
        )

        self.assertEqual(
            result["status"],
            "SKIPPED_NO_CONFIRMED_FACTS",
        )

        self.assertFalse(
            result["should_call_ai"]
        )

    def test_generation_request_allowed_with_facts(self):
        writer_input = {
            "status": "READY_FOR_WRITING",
            "topic": "Test Game",
            "confirmed_facts": [
                {
                    "claim": (
                        "The game was officially "
                        "announced."
                    ),
                    "status": "CONFIRMED",
                    "sources": [
                        "https://example.com/official"
                    ],
                }
            ],
            "seo": {
                "primary_keyword": "Test Game",
            },
        }

        result = build_generation_request(
            writer_input
        )

        self.assertEqual(
            result["status"],
            "READY_FOR_AI",
        )

        self.assertTrue(
            result["should_call_ai"]
        )

    # ======================================================
    # V2 — DRAFT SAFETY
    # ======================================================

    def test_generated_draft_never_publishable_before_validation(self):
        result = normalize_generated_draft(
            {
                "title": "Test Game",
                "content": (
                    "Le jeu a été officiellement "
                    "annoncé."
                ),
                "meta_description": (
                    "Informations confirmées."
                ),
            }
        )

        self.assertEqual(
            result["status"],
            "DRAFT_PENDING_VALIDATION",
        )

        self.assertFalse(
            result["publishable"]
        )

    def test_empty_generated_draft_is_blocked(self):
        result = normalize_generated_draft(
            {}
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_EMPTY_DRAFT",
        )

        self.assertFalse(
            result["publishable"]
        )

    def test_validator_blocks_unsupported_claim(self):
        validation = (
            validate_draft_against_fact_pack(
                draft={
                    "title": "Test Game",
                    "content": (
                        "Le jeu sortira le "
                        "29 septembre 2026."
                    ),
                },
                confirmed_facts=[
                    {
                        "claim": (
                            "The game was officially "
                            "announced."
                        ),
                        "status": "CONFIRMED",
                        "sources": [
                            "https://example.com/official"
                        ],
                    }
                ],
                unsupported_claims=[
                    (
                        "The game releases "
                        "September 29, 2026."
                    )
                ],
            )
        )

        self.assertEqual(
            validation["status"],
            "BLOCKED_UNSUPPORTED_CLAIMS",
        )

    def test_validated_draft_can_be_safe_not_published(self):
        result = apply_validation_result(
            {
                "status": (
                    "DRAFT_PENDING_VALIDATION"
                ),
                "title": "Test Game",
                "content": (
                    "Confirmed information."
                ),
                "publishable": False,
            },
            {
                "status": "VALIDATION_PASSED",
                "unsupported_claims": [],
            },
        )

        self.assertEqual(
            result["status"],
            "VALIDATED_DRAFT",
        )

        self.assertTrue(
            result["publishable"]
        )

        self.assertFalse(
            result.get("published", False)
        )

    # ======================================================
    # V3 — AI RESPONSE PARSING
    # ======================================================

    def test_parse_valid_ai_json(self):
        raw = """
        {
          "title": "Test Game : annonce officielle",
          "content": "Le jeu a été officiellement annoncé.",
          "meta_description": "Les informations confirmées."
        }
        """

        result = parse_ai_draft_response(
            raw
        )

        self.assertEqual(
            result["title"],
            "Test Game : annonce officielle",
        )

        self.assertIn(
            "officiellement annoncé",
            result["content"],
        )

    def test_parse_markdown_fenced_json(self):
        raw = """```json
        {
          "title": "Test Game",
          "content": "Information confirmée.",
          "meta_description": "Résumé."
        }
        ```"""

        result = parse_ai_draft_response(
            raw
        )

        self.assertEqual(
            result["title"],
            "Test Game",
        )

    def test_invalid_ai_response_is_blocked(self):
        result = parse_ai_draft_response(
            "This is not JSON."
        )

        self.assertEqual(
            result,
            {}
        )

    # ======================================================
    # V3 — REAL GENERATION FUNCTION
    # ======================================================

    def test_ai_not_called_without_confirmed_facts(self):
        client = ExplodingGroqClient()

        request = {
            "status": (
                "SKIPPED_NO_CONFIRMED_FACTS"
            ),
            "should_call_ai": False,
            "prompt": "",
        }

        result = generate_draft_with_ai(
            generation_request=request,
            client=client,
        )

        self.assertEqual(
            result["status"],
            "SKIPPED_NO_CONFIRMED_FACTS",
        )

        self.assertEqual(
            client.chat.completions.calls,
            0,
        )

    def test_ai_generates_non_publishable_draft(self):
        client = FakeGroqClient(
            """
            {
              "title": "Test Game : annonce officielle",
              "content": "Le jeu a été officiellement annoncé.",
              "meta_description": "Informations confirmées."
            }
            """
        )

        request = {
            "status": "READY_FOR_AI",
            "should_call_ai": True,
            "prompt": (
                "Write only from confirmed facts."
            ),
        }

        result = generate_draft_with_ai(
            generation_request=request,
            client=client,
        )

        self.assertEqual(
            client.chat.completions.calls,
            1,
        )

        self.assertEqual(
            result["status"],
            "DRAFT_PENDING_VALIDATION",
        )

        self.assertFalse(
            result["publishable"]
        )

    def test_malformed_ai_output_is_blocked(self):
        client = FakeGroqClient(
            "I ignored the JSON instruction."
        )

        request = {
            "status": "READY_FOR_AI",
            "should_call_ai": True,
            "prompt": "Generate draft.",
        }

        result = generate_draft_with_ai(
            generation_request=request,
            client=client,
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_INVALID_AI_RESPONSE",
        )

        self.assertFalse(
            result["publishable"]
        )

    def test_ai_exception_fails_closed(self):
        class FailingCompletions:
            def create(self, **kwargs):
                raise RuntimeError(
                    "quota unavailable"
                )

        class FailingChat:
            def __init__(self):
                self.completions = (
                    FailingCompletions()
                )

        class FailingClient:
            def __init__(self):
                self.chat = FailingChat()

        result = generate_draft_with_ai(
            generation_request={
                "status": "READY_FOR_AI",
                "should_call_ai": True,
                "prompt": "Generate draft.",
            },
            client=FailingClient(),
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_AI_UNAVAILABLE",
        )

        self.assertFalse(
            result["publishable"]
        )


if __name__ == "__main__":
    unittest.main()
