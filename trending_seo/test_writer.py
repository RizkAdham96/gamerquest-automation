import unittest

from writer import (
    build_final_validation_request,
    parse_final_validator_response,
    run_final_validator,
    finalize_validated_draft,
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
        return FakeResponse(
            self.content
        )


class FakeChat:
    def __init__(self, content):
        self.completions = (
            FakeCompletions(
                content
            )
        )


class FakeGroqClient:
    def __init__(self, content):
        self.chat = FakeChat(
            content
        )


class FailingCompletions:
    def create(self, **kwargs):
        raise RuntimeError(
            "validator unavailable"
        )


class FailingChat:
    def __init__(self):
        self.completions = (
            FailingCompletions()
        )


class FailingClient:
    def __init__(self):
        self.chat = FailingChat()


class TestWriterV4FinalSafetyGate(
    unittest.TestCase
):

    # ======================================================
    # FINAL VALIDATION REQUEST
    # ======================================================

    def test_no_confirmed_facts_blocks_validation(self):
        draft = {
            "status": (
                "DRAFT_PENDING_VALIDATION"
            ),
            "title": "Test Game",
            "content": (
                "Le jeu a été annoncé."
            ),
            "publishable": False,
        }

        result = (
            build_final_validation_request(
                draft=draft,
                confirmed_facts=[],
            )
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_NO_CONFIRMED_FACTS",
        )

        self.assertFalse(
            result["should_call_ai"]
        )

        self.assertFalse(
            result["publishable"]
        )


    def test_pending_draft_with_facts_can_be_validated(self):
        confirmed_facts = [
            {
                "claim": (
                    "The game was officially "
                    "announced."
                ),
                "status": "CONFIRMED",
                "sources": [
                    (
                        "https://example.com/"
                        "official"
                    )
                ],
            }
        ]

        draft = {
            "status": (
                "DRAFT_PENDING_VALIDATION"
            ),
            "title": (
                "Test Game : annonce officielle"
            ),
            "content": (
                "Le jeu a été officiellement "
                "annoncé."
            ),
            "meta_description": (
                "Informations confirmées."
            ),
            "publishable": False,
        }

        result = (
            build_final_validation_request(
                draft=draft,
                confirmed_facts=confirmed_facts,
            )
        )

        self.assertEqual(
            result["status"],
            "READY_FOR_FINAL_VALIDATION",
        )

        self.assertTrue(
            result["should_call_ai"]
        )

        self.assertFalse(
            result["publishable"]
        )


    def test_validation_request_contains_confirmed_facts(self):
        confirmed_facts = [
            {
                "claim": (
                    "The game was officially "
                    "announced."
                ),
                "status": "CONFIRMED",
                "sources": [
                    (
                        "https://example.com/"
                        "official"
                    )
                ],
            }
        ]

        draft = {
            "status": (
                "DRAFT_PENDING_VALIDATION"
            ),
            "title": "Test Game",
            "content": (
                "Le jeu a été officiellement "
                "annoncé."
            ),
            "publishable": False,
        }

        result = (
            build_final_validation_request(
                draft=draft,
                confirmed_facts=confirmed_facts,
            )
        )

        serialized = str(
            result
        )

        self.assertIn(
            (
                "The game was officially "
                "announced."
            ),
            serialized,
        )


    # ======================================================
    # VALIDATOR RESPONSE PARSING
    # ======================================================

    def test_parse_validator_pass_response(self):
        raw = """
        {
            "status": "VALIDATION_PASSED",
            "unsupported_claims": [],
            "reason": "All factual claims are supported."
        }
        """

        result = (
            parse_final_validator_response(
                raw
            )
        )

        self.assertEqual(
            result["status"],
            "VALIDATION_PASSED",
        )

        self.assertEqual(
            result["unsupported_claims"],
            [],
        )


    def test_parse_validator_block_response(self):
        raw = """
        {
            "status": "BLOCKED_UNSUPPORTED_CLAIMS",
            "unsupported_claims": [
                "The game releases September 29, 2026."
            ],
            "reason": "The release date is not supported."
        }
        """

        result = (
            parse_final_validator_response(
                raw
            )
        )

        self.assertEqual(
            result["status"],
            (
                "BLOCKED_UNSUPPORTED_CLAIMS"
            ),
        )

        self.assertEqual(
            len(
                result[
                    "unsupported_claims"
                ]
            ),
            1,
        )


    def test_invalid_validator_response_fails_closed(self):
        result = (
            parse_final_validator_response(
                "not valid json"
            )
        )

        self.assertEqual(
            result["status"],
            (
                "BLOCKED_INVALID_VALIDATOR_RESPONSE"
            ),
        )


    # ======================================================
    # REAL FINAL VALIDATOR FUNCTION
    # ======================================================

    def test_validator_passes_supported_article(self):
        client = FakeGroqClient(
            """
            {
                "status": "VALIDATION_PASSED",
                "unsupported_claims": [],
                "reason": "Article is grounded."
            }
            """
        )

        request = {
            "status": (
                "READY_FOR_FINAL_VALIDATION"
            ),
            "should_call_ai": True,
            "prompt": (
                "Validate this draft."
            ),
            "publishable": False,
        }

        result = run_final_validator(
            validation_request=request,
            client=client,
        )

        self.assertEqual(
            client.chat.completions.calls,
            1,
        )

        self.assertEqual(
            result["status"],
            "VALIDATION_PASSED",
        )


    def test_validator_blocks_invented_release_date(self):
        client = FakeGroqClient(
            """
            {
                "status": "BLOCKED_UNSUPPORTED_CLAIMS",
                "unsupported_claims": [
                    "The game releases September 29, 2026."
                ],
                "reason": "No confirmed fact supports the date."
            }
            """
        )

        result = run_final_validator(
            validation_request={
                "status": (
                    "READY_FOR_FINAL_VALIDATION"
                ),
                "should_call_ai": True,
                "prompt": (
                    "Validate draft with "
                    "release date."
                ),
                "publishable": False,
            },
            client=client,
        )

        self.assertEqual(
            result["status"],
            (
                "BLOCKED_UNSUPPORTED_CLAIMS"
            ),
        )

        self.assertFalse(
            result["publishable"]
        )


    def test_validator_blocks_invented_platform(self):
        client = FakeGroqClient(
            """
            {
                "status": "BLOCKED_UNSUPPORTED_CLAIMS",
                "unsupported_claims": [
                    "The game will launch on PS5."
                ],
                "reason": "PS5 is not supported by the fact pack."
            }
            """
        )

        result = run_final_validator(
            validation_request={
                "status": (
                    "READY_FOR_FINAL_VALIDATION"
                ),
                "should_call_ai": True,
                "prompt": (
                    "Validate draft."
                ),
                "publishable": False,
            },
            client=client,
        )

        self.assertEqual(
            result["status"],
            (
                "BLOCKED_UNSUPPORTED_CLAIMS"
            ),
        )


    def test_validator_failure_fails_closed(self):
        result = run_final_validator(
            validation_request={
                "status": (
                    "READY_FOR_FINAL_VALIDATION"
                ),
                "should_call_ai": True,
                "prompt": (
                    "Validate draft."
                ),
                "publishable": False,
            },
            client=FailingClient(),
        )

        self.assertEqual(
            result["status"],
            (
                "BLOCKED_VALIDATOR_UNAVAILABLE"
            ),
        )

        self.assertFalse(
            result["publishable"]
        )


    # ======================================================
    # FINAL ARTICLE STATE
    # ======================================================

    def test_passed_validation_creates_validated_draft(self):
        draft = {
            "status": (
                "DRAFT_PENDING_VALIDATION"
            ),
            "title": "Test Game",
            "content": (
                "Confirmed information only."
            ),
            "publishable": False,
            "published": False,
        }

        validation = {
            "status": (
                "VALIDATION_PASSED"
            ),
            "unsupported_claims": [],
        }

        result = finalize_validated_draft(
            draft=draft,
            validation=validation,
        )

        self.assertEqual(
            result["status"],
            "VALIDATED_DRAFT",
        )

        self.assertTrue(
            result["publishable"]
        )

        self.assertFalse(
            result["published"]
        )


    def test_failed_validation_never_becomes_publishable(self):
        draft = {
            "status": (
                "DRAFT_PENDING_VALIDATION"
            ),
            "title": "Test Game",
            "content": (
                "Unsupported release date."
            ),
            "publishable": False,
            "published": False,
        }

        validation = {
            "status": (
                "BLOCKED_UNSUPPORTED_CLAIMS"
            ),
            "unsupported_claims": [
                (
                    "Unsupported "
                    "release date."
                )
            ],
        }

        result = finalize_validated_draft(
            draft=draft,
            validation=validation,
        )

        self.assertEqual(
            result["status"],
            (
                "BLOCKED_UNSUPPORTED_CLAIMS"
            ),
        )

        self.assertFalse(
            result["publishable"]
        )

        self.assertFalse(
            result["published"]
        )


    def test_validator_can_never_mark_article_published(self):
        draft = {
            "status": (
                "DRAFT_PENDING_VALIDATION"
            ),
            "title": "Test Game",
            "content": (
                "Confirmed information."
            ),
            "publishable": False,
            "published": False,
        }

        validation = {
            "status": (
                "VALIDATION_PASSED"
            ),
            "unsupported_claims": [],
            "published": True,
        }

        result = finalize_validated_draft(
            draft=draft,
            validation=validation,
        )

        self.assertFalse(
            result["published"]
        )


if __name__ == "__main__":
    unittest.main()
