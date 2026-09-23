import unittest
from io import BytesIO

from PIL import Image

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
          <img
            src="https://images.example.com/gameplay/150x90.jpg"
            srcset="https://images.example.com/gameplay/640x360.jpg 640w, https://images.example.com/gameplay/1280x720.jpg 1280w"
            alt="Ocarina of Time Switch 2 gameplay">
          <img
            src="https://images.example.com/special-edition/150x90.jpg"
            srcset="https://images.example.com/special-edition/1280x720.jpg 1280w"
            alt="Zelda Switch 2 special edition console">
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
                "https://images.example.com/gameplay/1280x720.jpg",
                "https://images.example.com/special-edition/1280x720.jpg",
            ],
        )
        self.assertEqual(len(set(images)), 3)

    def test_inspects_gamerquest_article_url_as_additional_image_source(self):
        source_id = "article-456"
        articles = [
            {
                "source_id": source_id,
                "title": "Metroid Prime 4 Switch 2",
                "tags": ["Metroid Prime 4", "Switch 2"],
                "slug": "metroid-prime-4-switch-2",
                "featured_image": {
                    "url": "https://cdn.example.com/metroid-cover.jpg",
                },
            }
        ]

        requested = []

        def page_fetcher(url):
            requested.append(url)
            return """
            <html><body>
              <img src="https://cdn.example.com/metroid-gameplay.jpg"
                   alt="Metroid Prime 4 Switch 2 gameplay">
              <img src="https://cdn.example.com/metroid-world.jpg"
                   alt="Metroid Prime 4 Switch 2 world">
            </body></html>
            """

        images = render_fallback.resolve_featured_images(
            source_id,
            content_items=articles,
            page_fetcher=page_fetcher,
        )

        self.assertIn(
            "https://gamerquestfr.com/metroid-prime-4-switch-2/",
            requested,
        )
        self.assertEqual(len(images), 3)

    def test_upgrades_nintendolife_thumbnail_to_large_variant(self):
        self.assertEqual(
            render_fallback._upgrade_image_url(
                "https://images.nintendolife.com/a1222a9011485/150x90.jpg"
            ),
            "https://images.nintendolife.com/a1222a9011485/large.jpg",
        )

    def test_upgrades_wordpress_thumbnail_to_original_asset(self):
        self.assertEqual(
            render_fallback._upgrade_image_url(
                "https://example.com/uploads/game-320x180.jpg"
            ),
            "https://example.com/uploads/game.jpg",
        )

    def test_upgrades_youtube_thumbnail_to_max_resolution(self):
        self.assertEqual(
            render_fallback._upgrade_image_url(
                "https://i.ytimg.com/vi/example/hqdefault.jpg"
            ),
            "https://i.ytimg.com/vi/example/maxresdefault.jpg",
        )

    def test_upgrades_ign_numeric_rendition_to_original(self):
        self.assertEqual(
            render_fallback._upgrade_image_url(
                "https://sm.ign.com/t/ign_es/video/game-trailer.640.jpg"
            ),
            "https://sm.ign.com/t/ign_es/video/game-trailer.jpg",
        )

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


    def test_rejects_high_resolution_unrelated_article_images(self):
        source_id = "article-123"
        articles = [
            {
                "source_id": source_id,
                "title": "Final Fantasy VII Revelation release date",
                "tags": ["Final Fantasy VII", "Revelation", "Square Enix"],
                "source": {"url": "https://source.example.com/final-fantasy"},
                "featured_image": {
                    "url": "https://cdn.example.com/final-fantasy-vii-cover.jpg",
                },
            }
        ]

        html = """
        <html><body>
          <img src="https://cdn.example.com/unrelated-mario-4k.jpg"
               alt="Mario movie promotional artwork">
          <img src="https://cdn.example.com/cloud-gameplay-1.jpg"
               alt="Final Fantasy VII Revelation Cloud gameplay">
          <img src="https://cdn.example.com/tifa-gameplay-2.jpg"
               alt="Final Fantasy VII Revelation Tifa gameplay">
        </body></html>
        """

        images = render_fallback.resolve_featured_images(
            source_id,
            content_items=articles,
            page_fetcher=lambda url: html,
        )

        self.assertEqual(len(images), 3)
        self.assertNotIn(
            "https://cdn.example.com/unrelated-mario-4k.jpg",
            images,
        )

    def test_accepts_hashed_cdn_url_when_alt_text_matches_topic(self):
        keywords = {"zelda", "ocarina", "switch"}
        self.assertTrue(
            render_fallback._looks_like_content_image(
                "https://images.example.com/a1222a9011485/large.jpg",
                "Zelda Ocarina of Time Switch 2 gameplay",
                keywords,
            )
        )


    def _image_bytes(self, size, color, accent=None):
        image = Image.new("RGB", size, color)
        if accent is not None:
            width, height = size
            for x in range(max(1, width // 3)):
                for y in range(max(1, height // 3)):
                    image.putpixel((x, y), accent)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=92)
        return buffer.getvalue()

    def test_rejects_low_resolution_source_images(self):
        urls = [
            "https://cdn.example.com/a.jpg",
            "https://cdn.example.com/b.jpg",
            "https://cdn.example.com/c.jpg",
        ]
        payloads = {
            urls[0]: self._image_bytes((1400, 900), (220, 30, 30)),
            urls[1]: self._image_bytes((640, 360), (30, 220, 30)),
            urls[2]: self._image_bytes((1400, 900), (30, 30, 220)),
        }

        with self.assertRaisesRegex(RuntimeError, "too small"):
            render_fallback.validate_source_images(
                urls,
                image_fetcher=lambda url: payloads[url],
            )

    def test_rejects_same_artwork_served_from_different_urls(self):
        urls = [
            "https://cdn-a.example.com/art.jpg",
            "https://cdn-b.example.com/art-copy.jpg",
            "https://cdn.example.com/other.jpg",
        ]
        same_art = self._image_bytes(
            (1400, 900),
            (80, 80, 80),
            accent=(220, 20, 20),
        )
        payloads = {
            urls[0]: same_art,
            urls[1]: same_art,
            urls[2]: self._image_bytes(
                (1400, 900),
                (20, 80, 220),
                accent=(240, 220, 20),
            ),
        }

        with self.assertRaisesRegex(RuntimeError, "visually duplicated"):
            render_fallback.validate_source_images(
                urls,
                image_fetcher=lambda url: payloads[url],
            )

    def test_accepts_three_large_visually_distinct_images(self):
        urls = [
            "https://cdn.example.com/a.jpg",
            "https://cdn.example.com/b.jpg",
            "https://cdn.example.com/c.jpg",
        ]
        payloads = {
            urls[0]: self._image_bytes(
                (1400, 900),
                (220, 30, 30),
                accent=(20, 20, 20),
            ),
            urls[1]: self._image_bytes(
                (1400, 900),
                (30, 220, 30),
                accent=(240, 240, 240),
            ),
            urls[2]: self._image_bytes(
                (1400, 900),
                (30, 30, 220),
                accent=(220, 180, 30),
            ),
        }

        self.assertEqual(
            render_fallback.validate_source_images(
                urls,
                image_fetcher=lambda url: payloads[url],
            ),
            urls,
        )



if __name__ == "__main__":
    unittest.main()
