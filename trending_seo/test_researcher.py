import unittest

from researcher import (
    normalize_claim_status,
    should_allow_claim,
    build_verified_fact_pack,
)


class TestTrendingSeoResearcher(unittest.TestCase):

    def test_normalize_confirmed(self):
        self.assertEqual(
            normalize_claim_status("confirmed"),
            "CONFIRMED",
        )

    def test_invalid_status_becomes_unknown(self):
        self.assertEqual(
            normalize_claim_status("probably true"),
            "UNKNOWN",
        )

    def test_only_confirmed_claims_are_allowed(self):
        self.assertTrue(
            should_allow_claim("CONFIRMED")
        )

        self.assertFalse(
            should_allow_claim("UNCONFIRMED")
        )

        self.assertFalse(
            should_allow_claim("UNKNOWN")
        )

    def test_fact_pack_only_exposes_confirmed_claims(self):
        claims = [
            {
                "claim": "A remaster was officially announced.",
                "status": "CONFIRMED",
                "sources": ["https://example.com/official"],
            },
            {
                "claim": "The release date is September 29.",
                "status": "UNCONFIRMED",
                "sources": [],
            },
            {
                "claim": "The game includes a new map.",
                "status": "UNKNOWN",
                "sources": [],
            },
        ]

        result = build_verified_fact_pack(claims)

        self.assertEqual(
            len(result["confirmed_facts"]),
            1,
        )

        self.assertEqual(
            result["confirmed_facts"][0]["claim"],
            "A remaster was officially announced.",
        )

        self.assertEqual(
            len(result["blocked_claims"]),
            2,
        )

    def test_release_date_cannot_pass_without_confirmation(self):
        claims = [
            {
                "claim": "The release date is September 29, 2026.",
                "status": "UNKNOWN",
                "sources": [],
            }
        ]

        result = build_verified_fact_pack(claims)

        self.assertEqual(
            result["confirmed_facts"],
            [],
        )

        self.assertEqual(
            len(result["blocked_claims"]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
