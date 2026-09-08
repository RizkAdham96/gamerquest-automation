import unittest

from researcher import build_discovery_query


class TestEvergreenResearch(unittest.TestCase):
    """Evergreen discovery must search for durable guidance, not breaking news."""

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
