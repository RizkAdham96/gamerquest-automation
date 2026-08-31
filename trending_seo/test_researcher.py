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
    parse_discovery_feed,
    rank_discovered_sources,
    is_google_news_url,
    extract_publisher_url_from_google_news_html,
    resolve_discovery_url,

    # V6
    collect_usable_evidence,
    select_claims_for_verification,
    normalize_verification_result,
)


class TestTrendingSeoResearcher(unittest.TestCase):

    # =====================================================
    # CLAIM SAFETY
    # =====================================================

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

        result = build_verified_fact_pack(
            claims
        )

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

        result = build_verified_fact_pack(
            claims
        )

        self.assertEqual(
            result["confirmed_facts"],
            [],
        )

        self.assertEqual(
            len(result["blocked_claims"]),
            1,
        )

    # =====================================================
    # HTML
    # =====================================================

    def test_clean_html_removes_scripts_and_tags(self):
        raw_html = """
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

        text = clean_html_text(
            raw_html
        )

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
    # URL SAFETY
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
    # FETCH RESULT
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
    # JSON-LD
    # =====================================================

    def test_extract_json_ld_article_text(self):
        raw_html = """
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

        text = extract_json_ld_text(
            raw_html
        )

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
        raw_html = """
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

        text = extract_json_ld_text(
            raw_html
        )

        self.assertIn(
            "gamescom award 2026 winners",
            text,
        )

        self.assertIn(
            "The Witcher 3 Remastered won Best Trailer.",
            text,
        )

    def test_invalid_json_ld_does_not_crash(self):
        raw_html = """
        <script type="application/ld+json">
            { this is invalid json
        </script>
        """

        text = extract_json_ld_text(
            raw_html
        )

        self.assertEqual(
            text,
            "",
        )

    # =====================================================
    # EMBEDDED JSON
    # =====================================================

    def test_extract_next_data_text(self):
        raw_html = """
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

        text = extract_embedded_json_text(
            raw_html
        )

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
    # BEST CONTENT
    # =====================================================

    def test_structured_data_is_preferred_over_tiny_html_shell(self):
        raw_html = """
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

        text = extract_best_page_text(
            raw_html
        )

        self.assertIn(
            "The Witcher 3 Remastered",
            text,
        )

        self.assertIn(
            "officially revealed the remaster",
            text,
        )

    def test_plain_html_remains_fallback(self):
        raw_html = """
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

        text = extract_best_page_text(
            raw_html
        )

        self.assertIn(
            "Regular gaming article",
            text,
        )

        self.assertIn(
            "content is available directly",
            text,
        )

    # =====================================================
    # V4 SOURCE DISCOVERY
    # =====================================================

    def test_build_discovery_query_uses_topic_and_keyword(self):
        scored_topic = {
            "topic": "The Witcher 3: Wild Hunt Remastered",
            "seo": {
                "primary_keyword": "The Witcher 3 Remastered"
            },
        }

        query = build_discovery_query(
            scored_topic
        )

        self.assertIn(
            "The Witcher 3 Remastered",
            query,
        )

    def test_parse_discovery_feed_extracts_articles(self):
        xml = """
        <rss version="2.0">
          <channel>

            <item>
              <title>
                The Witcher 3 Remastered officially announced
              </title>

              <link>
                https://example.com/witcher-remastered
              </link>

              <pubDate>
                Sat, 29 Aug 2026 20:00:00 GMT
              </pubDate>

              <source url="https://example.com">
                Example Gaming
              </source>
            </item>

            <item>
              <title>
                Witcher remaster platforms revealed
              </title>

              <link>
                https://publisher.example.com/news
              </link>

              <pubDate>
                Sat, 29 Aug 2026 21:00:00 GMT
              </pubDate>

              <source url="https://publisher.example.com">
                Publisher
              </source>
            </item>

          </channel>
        </rss>
        """

        articles = parse_discovery_feed(
            xml
        )

        self.assertEqual(
            len(articles),
            2,
        )

        self.assertEqual(
            articles[0]["title"],
            "The Witcher 3 Remastered officially announced",
        )

        self.assertEqual(
            articles[0]["url"],
            "https://example.com/witcher-remastered",
        )

    def test_discovery_feed_rejects_non_http_urls(self):
        xml = """
        <rss version="2.0">
          <channel>

            <item>
              <title>Unsafe result</title>
              <link>file:///etc/passwd</link>
            </item>

          </channel>
        </rss>
        """

        articles = parse_discovery_feed(
            xml
        )

        self.assertEqual(
            articles,
            [],
        )

    def test_rank_discovered_sources_prefers_relevant_result(self):
        topic = {
            "topic": "The Witcher 3: Wild Hunt Remastered",
            "seo": {
                "primary_keyword": "The Witcher 3 Remastered"
            },
        }

        sources = [
            {
                "title": "Random gaming news today",
                "url": "https://example.com/random",
                "publisher": "Example",
            },
            {
                "title": "The Witcher 3 Remastered officially announced",
                "url": "https://example.com/witcher-remastered",
                "publisher": "Example Gaming",
            },
        ]

        ranked = rank_discovered_sources(
            topic,
            sources,
        )

        self.assertEqual(
            ranked[0]["url"],
            "https://example.com/witcher-remastered",
        )

    def test_duplicate_discovery_urls_are_removed(self):
        topic = {
            "topic": "The Witcher 3 Remastered",
            "seo": {
                "primary_keyword": "The Witcher 3 Remastered"
            },
        }

        sources = [
            {
                "title": "Witcher announcement",
                "url": "https://example.com/article",
                "publisher": "Example",
            },
            {
                "title": "Same Witcher announcement",
                "url": "https://example.com/article",
                "publisher": "Example",
            },
        ]

        ranked = rank_discovered_sources(
            topic,
            sources,
        )

        self.assertEqual(
            len(ranked),
            1,
        )

    # =====================================================
    # V5 GOOGLE NEWS URL RESOLUTION
    # =====================================================

    def test_google_news_url_is_detected(self):
        self.assertTrue(
            is_google_news_url(
                "https://news.google.com/rss/articles/ABC123"
            )
        )

        self.assertTrue(
            is_google_news_url(
                "https://news.google.com/articles/ABC123"
            )
        )

        self.assertFalse(
            is_google_news_url(
                "https://www.ign.com/articles/example"
            )
        )

    def test_extract_publisher_url_from_google_news_html(self):
        raw_html = """
        <html>
            <body>

                <a
                    href="https://www.ign.com/articles/witcher-remastered"
                >
                    Read full article
                </a>

            </body>
        </html>
        """

        result = (
            extract_publisher_url_from_google_news_html(
                raw_html,
                google_url=(
                    "https://news.google.com/"
                    "rss/articles/ABC123"
                ),
            )
        )

        self.assertEqual(
            result,
            "https://www.ign.com/articles/witcher-remastered",
        )

    def test_google_news_links_are_not_returned_as_publishers(self):
        raw_html = """
        <html>
            <body>

                <a href="https://news.google.com/articles/OTHER">
                    Another Google News page
                </a>

            </body>
        </html>
        """

        result = (
            extract_publisher_url_from_google_news_html(
                raw_html,
                google_url=(
                    "https://news.google.com/"
                    "rss/articles/ABC123"
                ),
            )
        )

        self.assertEqual(
            result,
            "",
        )

    def test_unsafe_publisher_urls_are_rejected(self):
        raw_html = """
        <html>
            <body>

                <a href="http://127.0.0.1/private">
                    Internal
                </a>

            </body>
        </html>
        """

        result = (
            extract_publisher_url_from_google_news_html(
                raw_html,
                google_url=(
                    "https://news.google.com/"
                    "rss/articles/ABC123"
                ),
            )
        )

        self.assertEqual(
            result,
            "",
        )

    def test_regular_discovery_url_does_not_need_resolution(self):
        result = resolve_discovery_url(
            "https://www.ign.com/articles/example",
            wrapper_html="",
        )

        self.assertEqual(
            result["status"],
            "DIRECT",
        )

        self.assertEqual(
            result["resolved_url"],
            "https://www.ign.com/articles/example",
        )

    def test_google_wrapper_is_not_evidence_if_unresolved(self):
        result = resolve_discovery_url(
            "https://news.google.com/rss/articles/ABC123",
            wrapper_html=(
                "<html>"
                "<body>Google News</body>"
                "</html>"
            ),
        )

        self.assertEqual(
            result["status"],
            "UNRESOLVED",
        )

        self.assertEqual(
            result["resolved_url"],
            "",
        )

        self.assertFalse(
            result["can_fetch_as_evidence"]
        )

    def test_google_wrapper_resolves_to_publisher(self):
        wrapper_html = """
        <html>
            <body>

                <a href="https://www.ign.com/articles/witcher-remastered">
                    IGN article
                </a>

            </body>
        </html>
        """

        result = resolve_discovery_url(
            "https://news.google.com/rss/articles/ABC123",
            wrapper_html=wrapper_html,
        )

        self.assertEqual(
            result["status"],
            "RESOLVED",
        )

        self.assertEqual(
            result["resolved_url"],
            "https://www.ign.com/articles/witcher-remastered",
        )

        self.assertTrue(
            result["can_fetch_as_evidence"]
        )

    # =====================================================
    # V6 AUTOMATIC CLAIM VERIFICATION
    # =====================================================

    def test_collect_evidence_only_uses_usable_sources(self):

        original_sources = [
            {
                "url": "https://official.example.com/article",
                "fetch_status": "USABLE",
                "text": (
                    "CD PROJEKT RED officially announced "
                    "The Witcher 3 Remastered."
                ),
            },
            {
                "url": "https://weak.example.com/article",
                "fetch_status": "WEAK",
                "text": "Tiny shell.",
            },
        ]

        discovered_sources = [
            {
                "resolved_url": "https://gaming.example.com/article",
                "fetch_status": "USABLE",
                "text": (
                    "The announcement was shown during "
                    "Gamescom Opening Night Live."
                ),
            },
            {
                "resolved_url": "",
                "fetch_status": "UNRESOLVED",
                "text": "",
            },
        ]

        evidence = collect_usable_evidence(
            original_sources,
            discovered_sources,
        )

        self.assertEqual(
            len(evidence),
            2,
        )

        urls = {
            item["url"]
            for item in evidence
        }

        self.assertIn(
            "https://official.example.com/article",
            urls,
        )

        self.assertIn(
            "https://gaming.example.com/article",
            urls,
        )

        self.assertNotIn(
            "https://weak.example.com/article",
            urls,
        )

    def test_empty_source_text_is_not_evidence(self):

        evidence = collect_usable_evidence(
            [
                {
                    "url": "https://example.com/empty",
                    "fetch_status": "USABLE",
                    "text": "",
                }
            ],
            [],
        )

        self.assertEqual(
            evidence,
            [],
        )

    def test_only_unknown_claims_are_selected_for_verification(self):

        claims = [
            {
                "claim": "Claim one",
                "status": "UNKNOWN",
                "sources": [],
            },
            {
                "claim": "Already confirmed",
                "status": "CONFIRMED",
                "sources": ["https://example.com"],
            },
            {
                "claim": "Claim two",
                "status": "UNKNOWN",
                "sources": [],
            },
        ]

        selected = select_claims_for_verification(
            claims,
            max_claims=3,
        )

        self.assertEqual(
            len(selected),
            2,
        )

        self.assertEqual(
            selected[0]["claim"],
            "Claim one",
        )

        self.assertEqual(
            selected[1]["claim"],
            "Claim two",
        )

    def test_verification_is_capped_at_three_claims(self):

        claims = [
            {
                "claim": f"Claim {number}",
                "status": "UNKNOWN",
                "sources": [],
            }
            for number in range(1, 7)
        ]

        selected = select_claims_for_verification(
            claims,
            max_claims=3,
        )

        self.assertEqual(
            len(selected),
            3,
        )

        self.assertEqual(
            selected[0]["claim"],
            "Claim 1",
        )

        self.assertEqual(
            selected[2]["claim"],
            "Claim 3",
        )

    def test_valid_confirmed_verification_is_preserved(self):

        result = normalize_verification_result(
            {
                "claim": "The remaster was officially announced.",
                "status": "CONFIRMED",
                "supporting_source_urls": [
                    "https://official.example.com/article"
                ],
                "reason": (
                    "The official page explicitly states "
                    "that the remaster was announced."
                ),
            },
            allowed_source_urls={
                "https://official.example.com/article",
            },
        )

        self.assertEqual(
            result["status"],
            "CONFIRMED",
        )

        self.assertEqual(
            result["supporting_source_urls"],
            [
                "https://official.example.com/article"
            ],
        )

    def test_confirmed_without_source_becomes_unknown(self):

        result = normalize_verification_result(
            {
                "claim": "The release date is September 29.",
                "status": "CONFIRMED",
                "supporting_source_urls": [],
                "reason": "No citation supplied.",
            },
            allowed_source_urls={
                "https://example.com/article",
            },
        )

        self.assertEqual(
            result["status"],
            "UNKNOWN",
        )

        self.assertEqual(
            result["supporting_source_urls"],
            [],
        )

    def test_confirmed_with_unapproved_source_becomes_unknown(self):

        result = normalize_verification_result(
            {
                "claim": "The release date is September 29.",
                "status": "CONFIRMED",
                "supporting_source_urls": [
                    "https://made-up-source.example.com/article"
                ],
                "reason": "Claimed support.",
            },
            allowed_source_urls={
                "https://official.example.com/article",
            },
        )

        self.assertEqual(
            result["status"],
            "UNKNOWN",
        )

        self.assertEqual(
            result["supporting_source_urls"],
            [],
        )

    def test_invalid_ai_status_becomes_unknown(self):

        result = normalize_verification_result(
            {
                "claim": "A claim",
                "status": "PROBABLY_TRUE",
                "supporting_source_urls": [
                    "https://official.example.com/article"
                ],
                "reason": "Maybe.",
            },
            allowed_source_urls={
                "https://official.example.com/article",
            },
        )

        self.assertEqual(
            result["status"],
            "UNKNOWN",
        )

    def test_unconfirmed_result_is_allowed_but_blocked_from_fact_pack(self):

        verification = normalize_verification_result(
            {
                "claim": "The release date is September 29.",
                "status": "UNCONFIRMED",
                "supporting_source_urls": [
                    "https://official.example.com/article"
                ],
                "reason": (
                    "The available source does not confirm "
                    "this release date."
                ),
            },
            allowed_source_urls={
                "https://official.example.com/article",
            },
        )

        claim = {
            "claim": verification["claim"],
            "status": verification["status"],
            "sources": verification[
                "supporting_source_urls"
            ],
        }

        fact_pack = build_verified_fact_pack(
            [claim]
        )

        self.assertEqual(
            fact_pack["confirmed_facts"],
            [],
        )

        self.assertEqual(
            len(fact_pack["blocked_claims"]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
