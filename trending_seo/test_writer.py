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
)


class TestTrendingSEOWriter(unittest.TestCase):

    # ==========================================================
    # V1 — FACT GATE
    # ==========================================================

    def test_zero_confirmed_facts_blocks_writer(self):
        research_record = {
            "fact_pack": {
                "confirmed_facts": [],
                "blocked_claims": [
                    {
                        "claim": (
                            "Unverified release date"
                        ),
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
                            "The game was officially announced."
                        ),
                        "status": "CONFIRMED",
                        "sources": [
                            (
                                "https://example.com/"
                                "official"
                            )
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
                "claim": (
                    "Confirmed announcement."
                ),
                "status": "CONFIRMED",
                "sources": [
                    (
                        "https://example.com/"
                        "official"
                    )
                ],
            },
            {
                "claim": (
                    "Possible release date."
                ),
                "status": "UNKNOWN",
                "sources": [],
            },
            {
                "claim": (
                    "Rumored platform."
                ),
                "status": "UNCONFIRMED",
                "sources": [],
            },
        ]

        result = filter_confirmed_facts(
            claims
        )

        self.assertEqual(
            len(result),
            1
        )

        self.assertEqual(
            result[0]["claim"],
            "Confirmed announcement.",
        )


    def test_confirmed_fact_requires_source(self):
        claims = [
            {
                "claim": (
                    "Claim without evidence."
                ),
                "status": "CONFIRMED",
                "sources": [],
            }
        ]

        result = filter_confirmed_facts(
            claims
        )

        self.assertEqual(
            result,
            []
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
                            (
                                "https://example.com/"
                                "official"
                            )
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

        writer_input = build_writer_input(
            research_record
        )

        serialized = str(
            writer_input
        )

        self.assertIn(
            "Official confirmed fact.",
            serialized,
        )

        self.assertNotIn(
            (
                "Secret unverified "
                "release date."
            ),
            serialized,
        )


    # ==========================================================
    # V2 — GENERATION REQUEST
    # ==========================================================

    def test_generation_request_blocked_without_facts(self):
        writer_input = {
            "status": (
                "SKIPPED_NO_CONFIRMED_FACTS"
            ),
            "topic": (
                "The Witcher 3 Remastered"
            ),
            "confirmed_facts": [],
        }

        result = build_generation_request(
            writer_input
        )

        self.assertEqual(
            result["status"],
            (
                "SKIPPED_NO_CONFIRMED_FACTS"
            ),
        )

        self.assertFalse(
            result["should_call_ai"]
        )


    def test_generation_request_allowed_with_facts(self):
        writer_input = {
            "status": (
                "READY_FOR_WRITING"
            ),
            "topic": (
                "The Witcher 3 Remastered"
            ),
            "confirmed_facts": [
                {
                    "claim": (
                        "The remaster was "
                        "officially announced."
                    ),
                    "status": "CONFIRMED",
                    "sources": [
                        (
                            "https://example.com/"
                            "official"
                        )
                    ],
                }
            ],
            "seo": {
                "primary_keyword": (
                    "The Witcher 3 Remastered"
                ),
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


    def test_generation_request_contains_only_confirmed_facts(self):
        writer_input = {
            "status": (
                "READY_FOR_WRITING"
            ),
            "topic": "Test Game",
            "confirmed_facts": [
                {
                    "claim": (
                        "Confirmed announcement."
                    ),
                    "status": "CONFIRMED",
                    "sources": [
                        (
                            "https://example.com/"
                            "official"
                        )
                    ],
                }
            ],
            "seo": {
                "primary_keyword": (
                    "Test Game"
                ),
            },
        }

        result = build_generation_request(
            writer_input
        )

        serialized = str(
            result
        )

        self.assertIn(
            "Confirmed announcement.",
            serialized,
        )

        self.assertNotIn(
            "Possible release date",
            serialized,
        )


    # ==========================================================
    # V2 — GENERATED DRAFT NORMALIZATION
    # ==========================================================

    def test_generated_draft_is_never_publishable_before_validation(self):
        raw_draft = {
            "title": (
                "Test Game : ce que l'on sait"
            ),
            "content": (
                "Le jeu a été officiellement annoncé."
            ),
            "meta_description": (
                "Toutes les informations confirmées."
            ),
        }

        result = normalize_generated_draft(
            raw_draft
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


    # ==========================================================
    # V2 — FINAL FACT VALIDATION
    # ==========================================================

    def test_validator_passes_fully_grounded_draft(self):
        confirmed_facts = [
            {
                "claim": (
                    "The game was officially announced."
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
            "title": (
                "Test Game : annonce officielle"
            ),
            "content": (
                "Le jeu a été officiellement annoncé."
            ),
            "meta_description": (
                "Le jeu a été officiellement annoncé."
            ),
        }

        validation = (
            validate_draft_against_fact_pack(
                draft=draft,
                confirmed_facts=confirmed_facts,
                unsupported_claims=[],
            )
        )

        self.assertEqual(
            validation["status"],
            "VALIDATION_PASSED",
        )

        self.assertEqual(
            validation["unsupported_claims"],
            [],
        )


    def test_validator_blocks_unsupported_release_date(self):
        confirmed_facts = [
            {
                "claim": (
                    "The game was officially announced."
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
            "title": (
                "Test Game sort le 29 septembre"
            ),
            "content": (
                "Le jeu a été officiellement annoncé "
                "et sortira le 29 septembre 2026."
            ),
            "meta_description": (
                "Date de sortie du jeu."
            ),
        }

        validation = (
            validate_draft_against_fact_pack(
                draft=draft,
                confirmed_facts=confirmed_facts,
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
            (
                "BLOCKED_UNSUPPORTED_CLAIMS"
            ),
        )

        self.assertEqual(
            len(
                validation[
                    "unsupported_claims"
                ]
            ),
            1,
        )


    def test_validator_blocks_unsupported_platform(self):
        confirmed_facts = [
            {
                "claim": (
                    "The game was officially announced."
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
            "title": (
                "Test Game annoncé"
            ),
            "content": (
                "Le jeu a été annoncé "
                "et sortira sur PS5."
            ),
            "meta_description": (
                "Annonce officielle."
            ),
        }

        validation = (
            validate_draft_against_fact_pack(
                draft=draft,
                confirmed_facts=confirmed_facts,
                unsupported_claims=[
                    (
                        "The game will release "
                        "on PS5."
                    )
                ],
            )
        )

        self.assertEqual(
            validation["status"],
            (
                "BLOCKED_UNSUPPORTED_CLAIMS"
            ),
        )


    # ==========================================================
    # V2 — APPLY VALIDATION
    # ==========================================================

    def test_draft_remains_blocked_when_validation_fails(self):
        draft = {
            "status": (
                "DRAFT_PENDING_VALIDATION"
            ),
            "title": (
                "Test Game"
            ),
            "content": (
                "Unsupported date included."
            ),
            "publishable": False,
        }

        validation = {
            "status": (
                "BLOCKED_UNSUPPORTED_CLAIMS"
            ),
            "unsupported_claims": [
                (
                    "Unsupported release date."
                )
            ],
        }

        result = apply_validation_result(
            draft,
            validation,
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


    def test_validated_draft_can_be_marked_safe_but_not_published(self):
        draft = {
            "status": (
                "DRAFT_PENDING_VALIDATION"
            ),
            "title": (
                "Test Game"
            ),
            "content": (
                "Only confirmed information."
            ),
            "publishable": False,
        }

        validation = {
            "status": (
                "VALIDATION_PASSED"
            ),
            "unsupported_claims": [],
        }

        result = apply_validation_result(
            draft,
            validation,
        )

        self.assertEqual(
            result["status"],
            "VALIDATED_DRAFT",
        )

        self.assertTrue(
            result["publishable"]
        )

        self.assertFalse(
            result.get(
                "published",
                False,
            )
        )


if __name__ == "__main__":
    unittest.main()
