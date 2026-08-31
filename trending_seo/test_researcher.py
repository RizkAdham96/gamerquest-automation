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
    build_discovery_query,
    normalize_discovery_url,
    score_evidence_candidate,
    rank_evidence_candidates,
    classify_evidence_quality,
)


class TestResearcher(unittest.TestCase):

    # =========================================================
    # Existing verification safety tests
    # =========================================================

    def test_normalize_confirmed(self):
        self.assertEqual(
            normalize_claim_status("CONFIRMED"),
            "CONFIRMED",
        )

    def test_normalize_unknown_status(self):
        self.assertEqual(
            normalize_claim_status("something-invalid"),
            "UNKNOWN",
        )

    def test_only_confirmed_claim_is_allowed(self):
        self.assertTrue(should_allow_claim("CONFIRMED"))
        self.assertFalse(should_allow_claim("UNKNOWN"))
        self.assertFalse(should_allow_claim("UNCONFIRMED"))

    def test_confirmed_claim_without_source_is_blocked(self):
        claims = [
            {
                "claim": "The game exists.",
                "status": "CONFIRMED",
                "sources": [],
            }
        ]

        pack = build_verified_fact_pack(claims)

        self.assertEqual(len(pack["confirmed_facts"]), 0)
        self.assertEqual(len(pack["blocked_claims"]), 1)

    def test_confirmed_claim_with_source_is_allowed(self):
        claims = [
            {
                "claim": "The game exists.",
                "status": "CONFIRMED",
                "sources": [
                    "https://example.com/official-announcement"
                ],
            }
        ]

        pack = build_verified_fact_pack(claims)

        self.assertEqual(len(pack["confirmed_facts"]), 1)
        self.assertEqual(len(pack["blocked_claims"]), 0)

    def test_unknown_release_date_is_blocked(self):
        claims = [
            {
                "claim": "The game releases September 29.",
                "status": "UNKNOWN",
                "sources": [],
            }
        ]

        pack = build_verified_fact_pack(claims)

        self.assertEqual(len(pack["confirmed_facts"]), 0)
        self.assertEqual(len(pack["blocked_claims"]), 1)

    # =========================================================
    # Existing HTML / fetch tests
    # =========================================================

    def test_clean_html_text_removes_scripts(self):
        raw_html = """
        <html>
            <head>
                <script>bad javascript</script>
                <style>.bad { color:red; }</style>
            </head>
            <body>
                <h1>Official announcement</h1>
                <p>The game has been announced.</p>
            </body>
        </html>
        """

        text = clean_html_text(raw_html)

        self.assertIn("Official announcement", text)
        self.assertIn("The game has been announced.", text)
        self.assertNotIn("bad javascript", text)
        self.assertNotIn("color:red", text)

    def test_safe_public_https_url(self):
        self.assertTrue(
            is_safe_public_url(
                "https://www.example.com/article"
            )
        )

    def test_localhost_is_blocked(self):
        self.assertFalse(
            is_safe_public_url(
                "http://127.0.0.1/private"
            )
        )

    def test_non_http_url_is_blocked(self):
        self.assertFalse(
            is_safe_public_url(
                "file:///etc/passwd"
            )
        )

    def test_usable_fetch_result(self):
        result = evaluate_fetch_result(
            status_code=200,
            text="Official announcement content.",
        )

        self.assertEqual(result, "USABLE")

    def test_empty_fetch_result_is_unusable(self):
        result = evaluate_fetch_result(
            status_code=200,
            text="",
        )

        self.assertEqual(result, "UNUSABLE")

    def test_403_fetch_result_is_unusable(self):
        result = evaluate_fetch_result(
            status_code=403,
            text="Forbidden",
        )

        self.assertEqual(result, "UNUSABLE")

    # =========================================================
    # Existing structured-data tests
    # =========================================================

    def test_extract_json_ld_article(self):
        raw_html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@type": "NewsArticle",
            "headline": "The Witcher 3 Remastered announced",
            "description": "CD Projekt announced the remaster.",
            "articleBody": "The remaster was shown during the event."
        }
        </script>
        </head>
        <body>Small shell</body>
        </html>
        """

        text = extract_json_ld_text(raw_html)

        self.assertIn(
            "The Witcher 3 Remastered announced",
            text,
        )
        self.assertIn(
            "CD Projekt announced the remaster.",
            text,
        )
        self.assertIn(
            "The remaster was shown during the event.",
            text,
        )

    def test_extract_json_ld_graph(self):
        raw_html = """
        <script type="application/ld+json">
        {
            "@graph": [
                {
                    "@type": "WebSite",
                    "name": "Gaming Site"
                },
                {
                    "@type": "NewsArticle",
                    "headline": "Major game announcement",
                    "articleBody": "This is the article content."
                }
            ]
        }
        </script>
        """

        text = extract_json_ld_text(raw_html)

        self.assertIn("Major game announcement", text)
        self.assertIn("This is the article content.", text)

    def test_invalid_json_ld_does_not_crash(self):
        raw_html = """
        <script type="application/ld+json">
        { this is invalid json }
        </script>
        """

        text = extract_json_ld_text(raw_html)

        self.assertEqual(text, "")

    def test_extract_next_data(self):
        raw_html = """
        <script id="__NEXT_DATA__" type="application/json">
        {
            "props": {
                "pageProps": {
                    "article": {
                        "title": "The Witcher 3 Remastered",
                        "description": "Official information",
                        "content": "The game was presented at the event."
                    }
                }
            }
        }
        </script>
        """

        text = extract_embedded_json_text(raw_html)

        self.assertIn("The Witcher 3 Remastered", text)
        self.assertIn("Official information", text)
        self.assertIn(
            "The game was presented at the event.",
            text,
        )

    def test_best_page_text_prefers_structured_data(self):
        raw_html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@type": "NewsArticle",
            "headline": "Important announcement",
            "articleBody": "Detailed verified article information."
        }
        </script>
        </head>
        <body>Site</body>
        </html>
        """

        text = extract_best_page_text(raw_html)

        self.assertIn("Important announcement", text)
        self.assertIn(
            "Detailed verified article information.",
            text,
        )

    def test_best_page_text_falls_back_to_html(self):
        raw_html = """
        <html>
        <body>
            <h1>Normal article</h1>
            <p>This article has useful information.</p>
        </body>
        </html>
        """

        text = extract_best_page_text(raw_html)

        self.assertIn("Normal article", text)
        self.assertIn(
            "This article has useful information.",
            text,
        )

    # =========================================================
    # Researcher v7 — evidence discovery tests
    # =========================================================

    def test_discovery_query_contains_topic(self):
        query = build_discovery_query(
            "The Witcher 3: Wild Hunt Remastered"
        )

        self.assertIn(
            "The Witcher 3",
            query,
        )

    def test_discovery_query_asks_for_authoritative_sources(self):
        query = build_discovery_query(
            "The Witcher 3 Remastered"
        ).lower()

        self.assertTrue(
            "official" in query
            or "announcement" in query
            or "news" in query
        )

    def test_google_news_redirect_url_is_not_final_evidence_url(self):
        google_url = (
            "https://news.google.com/rss/articles/"
            "CBMiExample"
        )

        normalized = normalize_discovery_url(google_url)

        self.assertNotEqual(normalized, google_url)

    def test_normalize_discovery_url_keeps_direct_publisher_url(self):
        url = (
            "https://www.gamespot.com/articles/"
            "witcher-remastered-announcement/"
        )

        normalized = normalize_discovery_url(url)

        self.assertEqual(normalized, url)

    def test_official_source_scores_higher_than_aggregator(self):
        official = {
            "url": "https://www.cdprojektred.com/news/witcher",
            "title": "Official Witcher announcement",
            "publisher": "CD PROJEKT RED",
            "source_type": "official",
        }

        aggregator = {
            "url": "https://example-aggregator.com/witcher",
            "title": "Witcher rumors",
            "publisher": "Example Aggregator",
            "source_type": "aggregator",
        }

        self.assertGreater(
            score_evidence_candidate(official),
            score_evidence_candidate(aggregator),
        )

    def test_direct_publisher_source_gets_positive_score(self):
        candidate = {
            "url": "https://www.ign.com/articles/witcher-remastered",
            "title": "The Witcher 3 Remastered announced",
            "publisher": "IGN",
            "source_type": "publisher",
        }

        self.assertGreater(
            score_evidence_candidate(candidate),
            0,
        )

    def test_unresolved_google_news_url_is_penalized(self):
        candidate = {
            "url": (
                "https://news.google.com/rss/articles/"
                "CBMiExample"
            ),
            "title": "Witcher story",
            "publisher": "Unknown",
            "source_type": "aggregator",
        }

        score = score_evidence_candidate(candidate)

        self.assertLess(score, 0)

    def test_rank_candidates_puts_official_first(self):
        candidates = [
            {
                "url": "https://example.com/story",
                "title": "Story",
                "publisher": "Example",
                "source_type": "aggregator",
            },
            {
                "url": "https://www.cdprojektred.com/news/witcher",
                "title": "Official announcement",
                "publisher": "CD PROJEKT RED",
                "source_type": "official",
            },
            {
                "url": "https://www.ign.com/articles/witcher",
                "title": "Witcher news",
                "publisher": "IGN",
                "source_type": "publisher",
            },
        ]

        ranked = rank_evidence_candidates(candidates)

        self.assertEqual(
            ranked[0]["source_type"],
            "official",
        )

    def test_rank_candidates_removes_duplicate_urls(self):
        candidates = [
            {
                "url": "https://www.ign.com/articles/witcher",
                "title": "Witcher",
                "publisher": "IGN",
                "source_type": "publisher",
            },
            {
                "url": "https://www.ign.com/articles/witcher",
                "title": "Duplicate Witcher",
                "publisher": "IGN",
                "source_type": "publisher",
            },
        ]

        ranked = rank_evidence_candidates(candidates)

        self.assertEqual(len(ranked), 1)

    def test_long_relevant_article_is_strong_evidence(self):
        text = (
            "The Witcher 3 Remastered was officially announced. "
            * 40
        )

        quality = classify_evidence_quality(
            text=text,
            topic="The Witcher 3 Remastered",
            status_code=200,
        )

        self.assertEqual(quality, "USABLE")

    def test_tiny_page_is_weak_evidence(self):
        quality = classify_evidence_quality(
            text="The Witcher 3 Remastered",
            topic="The Witcher 3 Remastered",
            status_code=200,
        )

        self.assertEqual(quality, "WEAK")

    def test_irrelevant_page_is_weak_evidence(self):
        text = (
            "This page discusses unrelated technology news. "
            * 30
        )

        quality = classify_evidence_quality(
            text=text,
            topic="The Witcher 3 Remastered",
            status_code=200,
        )

        self.assertEqual(quality, "WEAK")

    def test_failed_http_is_unusable_evidence(self):
        quality = classify_evidence_quality(
            text="Some content",
            topic="The Witcher 3 Remastered",
            status_code=403,
        )

        self.assertEqual(quality, "UNUSABLE")


if __name__ == "__main__":
    unittest.main()
