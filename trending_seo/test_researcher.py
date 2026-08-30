import unittest

from researcher import (
    normalize_claim_status,
    should_allow_claim,
    build_verified_fact_pack,
    clean_html_text,
    is_safe_public_url,
    evaluate_fetch_result,
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
                "sources": [
                    "https://example.com/official"
                ],
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

    # =====================================================
    # SOURCE FETCHING TESTS
    # =====================================================

    def test_clean_html_removes_scripts_and_tags(self):
        html = """
        <html>
            <head>
                <script>
                    alert("bad");
                </script>
                <style>
                    body { color: red; }
                </style>
            </head>

            <body>
                <h1>The Witcher 3 Remastered</h1>
                <p>Official announcement.</p>
            </body>
        </html>
        """

        text = clean_html_text(html)

        self.assertIn(
            "The Witcher 3 Remastered",
            text,
        )

        self.assertIn(
            "Official announcement.",
            text,
        )

        self.assertNotIn(
            "alert",
            text,
        )

        self.assertNotIn(
            "color: red",
            text,
        )

    def test_only_http_and_https_urls_are_allowed(self):
        self.assertTrue(
            is_safe_public_url(
                "https://example.com/article"
            )
        )

        self.assertTrue(
            is_safe_public_url(
                "http://example.com/article"
            )
        )

        self.assertFalse(
            is_safe_public_url(
                "file:///etc/passwd"
            )
        )

        self.assertFalse(
            is_safe_public_url(
                "ftp://example.com/file"
            )
        )

    def test_localhost_is_blocked(self):
        self.assertFalse(
            is_safe_public_url(
                "http://localhost:8000"
            )
        )

        self.assertFalse(
            is_safe_public_url(
                "http://127.0.0.1/test"
            )
        )

    def test_successful_fetch_is_usable(self):
        result = evaluate_fetch_result(
            status_code=200,
            text="Official announcement content.",
        )

        self.assertEqual(
            result,
            "USABLE",
        )

    def test_empty_page_is_not_usable(self):
        result = evaluate_fetch_result(
            status_code=200,
            text="",
        )

        self.assertEqual(
            result,
            "UNUSABLE",
        )

    def test_http_error_is_not_usable(self):
        result = evaluate_fetch_result(
            status_code=403,
            text="Forbidden",
        )

        self.assertEqual(
            result,
            "UNUSABLE",
        )


if __name__ == "__main__":
    unittest.main()
