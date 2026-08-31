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
    resolve_discovery_url,
    normalize_discovery_url,
    is_search_result_url,
    extract_feed_entries,
    discover_feed_candidates,
    deduplicate_candidates,
    rank_evidence_candidate,
    build_evidence_candidate_pool,
)


class TestResearcherV8(unittest.TestCase):

    # ==========================================================
    # CLAIM SAFETY
    # ==========================================================

    def test_normalize_confirmed(self):
        self.assertEqual(
            normalize_claim_status("confirmed"),
            "CONFIRMED"
        )

    def test_normalize_unconfirmed(self):
        self.assertEqual(
            normalize_claim_status("unconfirmed"),
            "UNCONFIRMED"
        )

    def test_normalize_unknown(self):
        self.assertEqual(
            normalize_claim_status("something-weird"),
            "UNKNOWN"
        )

    def test_only_confirmed_claim_is_allowed(self):
        self.assertTrue(should_allow_claim("CONFIRMED"))
        self.assertFalse(should_allow_claim("UNCONFIRMED"))
        self.assertFalse(should_allow_claim("UNKNOWN"))

    def test_confirmed_claim_without_source_is_blocked(self):
        claims = [
            {
                "claim": "A remaster exists.",
                "status": "CONFIRMED",
                "source_url": ""
            }
        ]

        pack = build_verified_fact_pack(claims)

        self.assertEqual(len(pack["confirmed_facts"]), 0)
        self.assertEqual(len(pack["blocked_claims"]), 1)

    def test_unknown_release_date_is_blocked(self):
        claims = [
            {
                "claim": "The game releases September 29.",
                "status": "UNKNOWN",
                "source_url": "https://example.com/article"
            }
        ]

        pack = build_verified_fact_pack(claims)

        self.assertEqual(len(pack["confirmed_facts"]), 0)
        self.assertEqual(len(pack["blocked_claims"]), 1)

    def test_confirmed_claim_with_source_is_allowed(self):
        claims = [
            {
                "claim": "The remaster was announced.",
                "status": "CONFIRMED",
                "source_url": "https://example.com/article"
            }
        ]

        pack = build_verified_fact_pack(claims)

        self.assertEqual(len(pack["confirmed_facts"]), 1)
        self.assertEqual(len(pack["blocked_claims"]), 0)

    # ==========================================================
    # HTML EXTRACTION
    # ==========================================================

    def test_clean_html_text(self):
        raw_html = """
        <html>
            <head>
                <style>.hidden { display:none; }</style>
                <script>console.log("bad")</script>
            </head>
            <body>
                <h1>The Witcher 3 Remastered</h1>
                <p>Official announcement content.</p>
            </body>
        </html>
        """

        text = clean_html_text(raw_html)

        self.assertIn("The Witcher 3 Remastered", text)
        self.assertIn("Official announcement content.", text)
        self.assertNotIn("console.log", text)
        self.assertNotIn("display:none", text)

    def test_fetch_result_usable(self):
        result = evaluate_fetch_result(
            status_code=200,
            text="Official announcement content."
        )

        self.assertEqual(result, "USABLE")

    def test_fetch_result_empty_is_unusable(self):
        result = evaluate_fetch_result(
            status_code=200,
            text=""
        )

        self.assertEqual(result, "UNUSABLE")

    def test_fetch_result_403_is_unusable(self):
        result = evaluate_fetch_result(
            status_code=403,
            text="Forbidden"
        )

        self.assertEqual(result, "UNUSABLE")

    # ==========================================================
    # SAFE URLS
    # ==========================================================

    def test_http_url_is_safe(self):
        self.assertTrue(
            is_safe_public_url("https://example.com/article")
        )

    def test_localhost_is_blocked(self):
        self.assertFalse(
            is_safe_public_url("http://localhost/test")
        )

    def test_loopback_is_blocked(self):
        self.assertFalse(
            is_safe_public_url("http://127.0.0.1/test")
        )

    def test_non_http_scheme_is_blocked(self):
        self.assertFalse(
            is_safe_public_url("file:///etc/passwd")
        )

    # ==========================================================
    # STRUCTURED DATA
    # ==========================================================

    def test_extract_json_ld_article(self):
        raw_html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "The Witcher 3 Remastered",
            "description": "A remastered version was announced.",
            "articleBody": "CD PROJEKT RED announced the remaster."
        }
        </script>
        </head>
        </html>
        """

        text = extract_json_ld_text(raw_html)

        self.assertIn("The Witcher 3 Remastered", text)
        self.assertIn("A remastered version was announced.", text)
        self.assertIn(
            "CD PROJEKT RED announced the remaster.",
            text
        )

    def test_extract_json_ld_graph(self):
        raw_html = """
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "WebSite",
                    "name": "Gaming Site"
                },
                {
                    "@type": "NewsArticle",
                    "headline": "Witcher Remaster Announcement",
                    "articleBody": "Official article body."
                }
            ]
        }
        </script>
        """

        text = extract_json_ld_text(raw_html)

        self.assertIn("Witcher Remaster Announcement", text)
        self.assertIn("Official article body.", text)

    def test_invalid_json_ld_does_not_crash(self):
        raw_html = """
        <script type="application/ld+json">
        { invalid json }
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
                        "description": "Announcement details",
                        "content": "Full article content here."
                    }
                }
            }
        }
        </script>
        """

        text = extract_embedded_json_text(raw_html)

        self.assertIn("The Witcher 3 Remastered", text)
        self.assertIn("Announcement details", text)
        self.assertIn("Full article content here.", text)

    def test_best_page_text_prefers_structured_content(self):
        raw_html = """
        <html>
            <body>Small shell</body>
            <script type="application/ld+json">
            {
                "@type": "NewsArticle",
                "headline": "Important Headline",
                "articleBody":
                    "This is the actual useful article content."
            }
            </script>
        </html>
        """

        text = extract_best_page_text(raw_html)

        self.assertIn("Important Headline", text)
        self.assertIn(
            "This is the actual useful article content.",
            text
        )

    def test_best_page_text_has_html_fallback(self):
        raw_html = """
        <html>
            <body>
                <h1>Normal Article</h1>
                <p>Normal article content.</p>
            </body>
        </html>
        """

        text = extract_best_page_text(raw_html)

        self.assertIn("Normal Article", text)
        self.assertIn("Normal article content.", text)

    # ==========================================================
    # DISCOVERY QUERY
    # ==========================================================

    def test_build_discovery_query(self):
        query = build_discovery_query(
            topic="The Witcher 3 Remastered",
            claim="The remaster was officially announced."
        )

        self.assertIn("The Witcher 3 Remastered", query)
        self.assertIn("officially announced", query)

    # ==========================================================
    # URL NORMALIZATION
    # ==========================================================

    def test_normalize_discovery_url(self):
        url = normalize_discovery_url(
            "  https://example.com/news/article#comments  "
        )

        self.assertEqual(
            url,
            "https://example.com/news/article"
        )

    def test_normalize_discovery_url_removes_tracking(self):
        url = normalize_discovery_url(
            "https://example.com/article"
            "?utm_source=google&utm_medium=search&id=123"
        )

        self.assertEqual(
            url,
            "https://example.com/article?id=123"
        )

    # ==========================================================
    # SEARCH RESULT URL PROTECTION
    # ==========================================================

    def test_google_search_url_is_not_evidence(self):
        self.assertTrue(
            is_search_result_url(
                "https://www.google.com/search?q=witcher"
            )
        )

    def test_google_redirect_url_is_not_evidence(self):
        self.assertTrue(
            is_search_result_url(
                "https://www.google.com/url?q="
                "https://example.com/article"
            )
        )

    def test_direct_publisher_url_is_not_search_result(self):
        self.assertFalse(
            is_search_result_url(
                "https://www.gamespot.com/articles/example/"
            )
        )

    def test_resolve_discovery_url_extracts_google_target(self):
        url = (
            "https://www.google.com/url?"
            "q=https%3A%2F%2Fexample.com%2Farticle"
        )

        resolved = resolve_discovery_url(url)

        self.assertEqual(
            resolved,
            "https://example.com/article"
        )

    # ==========================================================
    # RSS / ATOM EXTRACTION
    # ==========================================================

    def test_extract_rss_entries(self):
        feed = """
        <rss version="2.0">
          <channel>
            <title>Gaming News</title>
            <item>
              <title>The Witcher 3 Remastered announced</title>
              <link>https://example.com/witcher-remastered</link>
              <description>
                CD PROJEKT RED announces a remaster.
              </description>
            </item>
          </channel>
        </rss>
        """

        entries = extract_feed_entries(feed)

        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0]["url"],
            "https://example.com/witcher-remastered"
        )
        self.assertIn(
            "Witcher",
            entries[0]["title"]
        )

    def test_extract_atom_entries(self):
        feed = """
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Gaming Feed</title>
          <entry>
            <title>Witcher Remaster News</title>
            <link
              href="https://example.com/witcher-news"
              rel="alternate"
            />
            <summary>Official remaster information.</summary>
          </entry>
        </feed>
        """

        entries = extract_feed_entries(feed)

        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0]["url"],
            "https://example.com/witcher-news"
        )

    def test_discover_feed_candidates_matches_topic(self):
        feed = """
        <rss version="2.0">
          <channel>
            <item>
              <title>The Witcher 3 Remastered announced</title>
              <link>https://example.com/witcher</link>
              <description>
                Information about The Witcher 3 Remastered.
              </description>
            </item>
            <item>
              <title>Completely unrelated game</title>
              <link>https://example.com/other</link>
              <description>Other news.</description>
            </item>
          </channel>
        </rss>
        """

        candidates = discover_feed_candidates(
            feed_text=feed,
            topic="The Witcher 3 Remastered"
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["url"],
            "https://example.com/witcher"
        )

    # ==========================================================
    # DEDUPLICATION
    # ==========================================================

    def test_deduplicate_candidates(self):
        candidates = [
            {
                "url": "https://example.com/article",
                "source_type": "rss"
            },
            {
                "url": "https://example.com/article#comments",
                "source_type": "search"
            },
            {
                "url": "https://example.com/other",
                "source_type": "official"
            }
        ]

        result = deduplicate_candidates(candidates)

        self.assertEqual(len(result), 2)

    # ==========================================================
    # EVIDENCE RANKING
    # ==========================================================

    def test_official_source_ranks_above_search(self):
        official = {
            "url": "https://thewitcher.com/news/example",
            "source_type": "official",
            "publisher_match": True,
            "usable": True
        }

        search = {
            "url": "https://example.com/article",
            "source_type": "search",
            "publisher_match": False,
            "usable": True
        }

        self.assertGreater(
            rank_evidence_candidate(official),
            rank_evidence_candidate(search)
        )

    def test_usable_candidate_ranks_above_unusable(self):
        usable = {
            "url": "https://example.com/a",
            "source_type": "publisher",
            "publisher_match": True,
            "usable": True
        }

        unusable = {
            "url": "https://example.com/b",
            "source_type": "publisher",
            "publisher_match": True,
            "usable": False
        }

        self.assertGreater(
            rank_evidence_candidate(usable),
            rank_evidence_candidate(unusable)
        )

    def test_search_result_page_gets_zero_rank(self):
        candidate = {
            "url": "https://www.google.com/search?q=witcher",
            "source_type": "search",
            "publisher_match": False,
            "usable": True
        }

        self.assertEqual(
            rank_evidence_candidate(candidate),
            0
        )

    # ==========================================================
    # EVIDENCE POOL
    # ==========================================================

    def test_build_evidence_pool_rejects_search_pages(self):
        candidates = [
            {
                "url": "https://www.google.com/search?q=witcher",
                "source_type": "search",
                "publisher_match": False,
                "usable": True
            },
            {
                "url": "https://example.com/witcher",
                "source_type": "rss",
                "publisher_match": True,
                "usable": True
            }
        ]

        pool = build_evidence_candidate_pool(candidates)

        urls = [item["url"] for item in pool]

        self.assertNotIn(
            "https://www.google.com/search?q=witcher",
            urls
        )

        self.assertIn(
            "https://example.com/witcher",
            urls
        )

    def test_evidence_pool_is_sorted_best_first(self):
        candidates = [
            {
                "url": "https://example.com/search-result",
                "source_type": "search",
                "publisher_match": False,
                "usable": True
            },
            {
                "url": "https://thewitcher.com/news/official",
                "source_type": "official",
                "publisher_match": True,
                "usable": True
            }
        ]

        pool = build_evidence_candidate_pool(candidates)

        self.assertEqual(
            pool[0]["url"],
            "https://thewitcher.com/news/official"
        )


if __name__ == "__main__":
    unittest.main()
