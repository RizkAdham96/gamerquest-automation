import unittest

from writer import (
    build_writer_input,
    can_generate_article,
    filter_confirmed_facts,
)


class TestTrendingSEOWriter(unittest.TestCase):

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
            can_generate_article(research_record)
        )

    def test_writer_allowed_with_confirmed_fact(self):
        research_record = {
            "fact_pack": {
                "confirmed_facts": [
                    {
                        "claim": "The game was officially announced.",
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
            can_generate_article(research_record)
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

        result = filter_confirmed_facts(claims)

        self.assertEqual(len(result), 1)
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

        result = filter_confirmed_facts(claims)

        self.assertEqual(result, [])

    def test_writer_input_excludes_blocked_claims(self):
        research_record = {
            "id": "test-topic",
            "topic": "Test Game",
            "fact_pack": {
                "confirmed_facts": [
                    {
                        "claim": "Official confirmed fact.",
                        "status": "CONFIRMED",
                        "sources": [
                            "https://example.com/official"
                        ],
                    }
                ],
                "blocked_claims": [
                    {
                        "claim": "Secret unverified release date.",
                        "status": "UNKNOWN",
                    }
                ],
            },
        }

        writer_input = build_writer_input(
            research_record
        )

        serialized = str(writer_input)

        self.assertIn(
            "Official confirmed fact.",
            serialized,
        )

        self.assertNotIn(
            "Secret unverified release date.",
            serialized,
        )


if __name__ == "__main__":
    unittest.main()
