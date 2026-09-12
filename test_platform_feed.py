import unittest

from enrich_platforms import enrich_article


class PlatformFeedTests(unittest.TestCase):
    def test_enrich_article_adds_platforms_and_platform_tags(self):
        article = {
            "title": "Nintendo Direct recap",
            "excerpt": "Also coming to PS5.",
            "content": "<p>Xbox Game Pass is included.</p>",
            "tags": ["Switch 2"],
            "seo": {
                "primary_keyword": "Nintendo Direct",
            },
        }

        enriched = enrich_article(article)

        self.assertEqual(
            enriched["platforms"],
            ["Nintendo", "PlayStation", "Xbox"],
        )
        self.assertEqual(
            enriched["tags"],
            ["Switch 2", "Nintendo", "PlayStation", "Xbox"],
        )


if __name__ == "__main__":
    unittest.main()
