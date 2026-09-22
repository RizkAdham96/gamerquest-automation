import unittest

from researcher import build_discovery_query


class TestEvergreenResearch(unittest.TestCase):
    """Evergreen discovery must search for durable guidance, not breaking news."""

    def test_publisher_feed_evidence_can_survive_blocked_page_fetch(self):
        import researcher

        topic = {
            "sources": [{
                "type": "publisher",
                "url": "https://example.com/game-story",
                "title": "Example game story",
                "evidence": "<p>This publisher feed contains enough factual context about the game to remain useful when the article page blocks automated fetches.</p>",
            }]
        }
        evidence = researcher.collect_seed_evidence(topic)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["evidence_origin"], "publisher_feed")
        self.assertIn("publisher feed contains enough factual context", evidence[0]["text"])

    def test_evergreen_discovery_uses_primary_keyword_not_news_suffix(self):
        # Primary keyword stays the search anchor; durable modifiers replace news wording.
        query = build_discovery_query({
            "topic": "Jeux comme Elden Ring",
            "seo": {"primary_keyword": "jeux comme Elden Ring"},
        })
        self.assertIn("jeux comme Elden Ring", query)
        self.assertNotIn("official announcement news", query.lower())
        self.assertIn("guide", query.lower())


if __name__ == "__main__":
    unittest.main()
