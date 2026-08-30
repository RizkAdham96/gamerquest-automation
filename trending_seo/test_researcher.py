import unittest

from researcher import (
    normalize_claim_status,
    should_allow_claim,
    build_verified_fact_pack,
    clean_html_text,
    is_safe_public_url,
    evaluate_fetch_result,
    extract_json_ld_text,
    extract_embedded_json_text,
    extract_best_page_text,
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
    # HTML TESTS
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

    # =====================================================
    # URL SAFETY TESTS
    # =====================================================

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

    # =====================================================
    # FETCH RESULT TESTS
    # =====================================================

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

    # =====================================================
    # JSON-LD EXTRACTION TESTS
    # =====================================================

    def test_extract_json_ld_article_text(self):
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "NewsArticle",
                    "headline": "The Witcher 3 Remastered announced",
                    "description": "CD PROJEKT RED revealed the remaster.",
                    "articleBody": "The remaster was announced during Gamescom 2026."
                }
                </script>
            </head>

            <body></body>
        </html>
        """

        text = extract_json_ld_text(html)

        self.assertIn(
            "The Witcher 3 Remastered announced",
            text,
        )

        self.assertIn(
            "CD PROJEKT RED revealed the remaster.",
            text,
        )

        self.assertIn(
            "The remaster was announced during Gamescom 2026.",
            text,
        )

    def test_extract_json_ld_from_graph(self):
        html = """
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "WebSite",
                    "name": "gamescom"
                },
                {
                    "@type": "NewsArticle",
                    "headline": "gamescom award 2026 winners",
                    "articleBody": "The Witcher 3 Remastered won Best Trailer."
                }
            ]
        }
        </script>
        """

        text = extract_json_ld_text(html)

        self.assertIn(
            "gamescom award 2026 winners",
            text,
        )

        self.assertIn(
            "The Witcher 3 Remastered won Best Trailer.",
            text,
        )

    def test_invalid_json_ld_does_not_crash(self):
        html = """
        <script type="application/ld+json">
            { this is invalid json
        </script>
        """

        text = extract_json_ld_text(html)

        self.assertEqual(
            text,
            "",
        )

    # =====================================================
    # EMBEDDED JSON TESTS
    # =====================================================

    def test_extract_next_data_text(self):
        html = """
        <html>
            <body>
                <script id="__NEXT_DATA__" type="application/json">
                {
                    "props": {
                        "pageProps": {
                            "title": "The Witcher 3 Remastered",
                            "description": "Official Gamescom announcement",
                            "content": "The remaster appeared during Opening Night Live."
                        }
                    }
                }
                </script>
            </body>
        </html>
        """

        text = extract_embedded_json_text(html)

        self.assertIn(
            "The Witcher 3 Remastered",
            text,
        )

        self.assertIn(
            "Official Gamescom announcement",
            text,
        )

        self.assertIn(
            "The remaster appeared during Opening Night Live.",
            text,
        )

    # =====================================================
    # BEST CONTENT SELECTION
    # =====================================================

    def test_structured_data_is_preferred_over_tiny_html_shell(self):
        html = """
        <html>
            <head>
                <title>gamescom</title>

                <script type="application/ld+json">
                {
                    "@type": "NewsArticle",
                    "headline": "The Witcher 3 Remastered",
                    "articleBody": "CD PROJEKT RED officially revealed the remaster during Gamescom."
                }
                </script>
            </head>

            <body>
                <div id="app"></div>
            </body>
        </html>
        """

        text = extract_best_page_text(html)

        self.assertIn(
            "The Witcher 3 Remastered",
            text,
        )

        self.assertIn(
            "officially revealed the remaster",
            text,
        )

    def test_plain_html_remains_fallback(self):
        html = """
        <html>
            <body>
                <h1>Regular gaming article</h1>
                <p>
                    This page does not use structured data,
                    but the content is available directly.
                </p>
            </body>
        </html>
        """

        text = extract_best_page_text(html)

        self.assertIn(
            "Regular gaming article",
            text,
        )

        self.assertIn(
            "content is available directly",
            text,
        )


if __name__ == "__main__":
    unittest.main()
    build_discovery_query,
    parse_discovery_feed,
    rank_discovered_sources,
