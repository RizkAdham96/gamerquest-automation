import unittest

from social import render_fallback


class TestFallbackSourceImage(unittest.TestCase):
    def test_resolves_article_featured_image_for_selected_source(self):
        source_id = "article-123"
        articles = [
            {
                "source_id": source_id,
                "featured_image": {
                    "url": "https://cdn.example.com/gamerquest-article.jpg",
                    "source_image_url": "https://source.example.com/game.jpg",
                },
            }
        ]

        image = render_fallback.resolve_featured_image(
            source_id,
            content_items=articles,
        )

        self.assertEqual(
            image,
            "https://cdn.example.com/gamerquest-article.jpg",
        )

    def test_refuses_gradient_only_render_when_selected_source_has_no_image(self):
        with self.assertRaisesRegex(RuntimeError, "no relevant featured image"):
            render_fallback.resolve_featured_image(
                "article-123",
                content_items=[{"source_id": "article-123"}],
            )


if __name__ == "__main__":
    unittest.main()
