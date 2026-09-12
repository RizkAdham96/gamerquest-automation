import unittest

from social import render_fallback


class TestFallbackSourceImage(unittest.TestCase):
    def test_resolves_three_unique_relevant_images_for_selected_source(self):
        source_id = "article-123"
        articles = [
            {
                "source_id": source_id,
                "title": "Ocarina of Time remake Switch 2",
                "tags": ["Zelda", "Ocarina of Time", "Switch 2"],
                "source": {"url": "https://source.example.com/zelda-article"},
                "featured_image": {
                    "url": "https://cdn.example.com/zelda-cover.jpg",
                    "source_image_url": "https://source.example.com/zelda-cover.jpg",
                },
            }
        ]

        html = """
        <html><head>
          <meta property="og:image" content="https://source.example.com/zelda-cover.jpg">
        </head><body>
          <img src="https://source.example.com/site-logo.png" alt="Site logo">
          <img src="https://source.example.com/zelda-gameplay.jpg" alt="Ocarina of Time Switch 2 gameplay">
          <img src="https://source.example.com/zelda-special-edition.jpg" alt="Zelda Switch 2 special edition console">
        </body></html>
        """

        images = render_fallback.resolve_featured_images(
            source_id,
            content_items=articles,
            page_fetcher=lambda url: html,
        )

        self.assertEqual(
            images,
            [
                "https://cdn.example.com/zelda-cover.jpg",
                "https://source.example.com/zelda-gameplay.jpg",
                "https://source.example.com/zelda-special-edition.jpg",
            ],
        )
        self.assertEqual(len(set(images)), 3)

    def test_refuses_render_when_three_unique_relevant_images_cannot_be_found(self):
        articles = [
            {
                "source_id": "article-123",
                "title": "Example game",
                "source": {"url": "https://source.example.com/article"},
                "featured_image": {"url": "https://cdn.example.com/only-one.jpg"},
            }
        ]

        with self.assertRaisesRegex(RuntimeError, "three unique relevant images"):
            render_fallback.resolve_featured_images(
                "article-123",
                content_items=articles,
                page_fetcher=lambda url: "<html><body><img src='https://cdn.example.com/only-one.jpg'></body></html>",
            )


if __name__ == "__main__":
    unittest.main()
