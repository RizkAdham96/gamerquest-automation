import unittest
from io import BytesIO

from PIL import Image

from social import render_fallback, steam_art


def _noise_image(size, seed):
    """Detailed, mutually distinct artwork that passes the quality gates."""
    width, height = size
    small = Image.effect_noise((width // 8, height // 8), 90).convert("RGB")
    tint = Image.new("RGB", small.size, ((seed * 70) % 255, (seed * 130) % 255, 90))
    image = Image.blend(small, tint, 0.45).resize(size)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _details(shots=3):
    return {
        "type": "game",
        "screenshots": [
            {"path_full": f"https://shared.akamai.steamstatic.com/apps/9/ss_{index}.1920x1080.jpg"}
            for index in range(shots)
        ],
    }


class TestCandidateGameNames(unittest.TestCase):
    def test_news_subject_is_the_title_head(self):
        item = {
            "title": "Grounded 2 – notes de mise à jour 0.5.1 : correctifs",
            "tags": ["Grounded 2", "patch notes", "bugs"],
        }
        self.assertEqual(steam_art.candidate_game_names(item), ["Grounded 2"])

    def test_franchise_tag_cannot_stand_in_for_a_sequel(self):
        item = {
            "title": "Call of Duty Modern Warfare 4 : date de sortie et double XP",
            "tags": ["Call of Duty", "Modern Warfare 4"],
        }
        self.assertEqual(
            steam_art.candidate_game_names(item), ["Call of Duty Modern Warfare 4"]
        )

    def test_roundup_without_separator_has_no_subject(self):
        item = {"title": "Les 7 meilleurs jeux similaires à Silksong", "tags": ["Silksong"]}
        self.assertEqual(steam_art.candidate_game_names(item), [])

    def test_deal_names_its_game_outright(self):
        item = {"title": "Cyberpunk 2077 à -70% sur Steam", "deal": {"game": "Cyberpunk 2077"}}
        self.assertEqual(steam_art.candidate_game_names(item), ["Cyberpunk 2077"])


class TestSteamScreenshots(unittest.TestCase):
    def setUp(self):
        steam_art._CACHE.clear()

    def test_returns_gallery_and_caches_the_lookup(self):
        calls = []

        def search(name):
            calls.append(name)
            return {"id": 9}

        item = {"title": "Grounded 2 – notes de mise à jour"}
        first = steam_art.steam_screenshots_for_item(item, search, lambda appid: _details())
        second = steam_art.steam_screenshots_for_item(item, search, lambda appid: _details())
        self.assertEqual(len(first), 3)
        self.assertEqual(first, second)
        self.assertEqual(calls, ["Grounded 2"])

    def test_unreachable_steam_falls_back_to_no_art(self):
        def failing(name):
            raise RuntimeError("steam down")

        item = {"title": "Grounded 2 – notes de mise à jour"}
        self.assertEqual(
            steam_art.steam_screenshots_for_item(item, failing, lambda appid: _details()), []
        )

    def test_dlc_and_unmatched_names_yield_nothing(self):
        item = {"title": "Grounded 2 – notes de mise à jour"}
        self.assertEqual(
            steam_art.steam_screenshots_for_item(item, lambda name: None, lambda appid: _details()),
            [],
        )
        steam_art._CACHE.clear()
        self.assertEqual(
            steam_art.steam_screenshots_for_item(
                item, lambda name: {"id": 9}, lambda appid: {**_details(), "type": "dlc"}
            ),
            [],
        )


class TestCarouselImageSelection(unittest.TestCase):
    def test_steam_screenshots_outrank_every_other_source(self):
        selected = {
            "source_id": "grounded",
            "title": "Grounded 2 – notes de mise à jour 0.5.1",
            "slug": "grounded-2-patch-notes",
            "featured_image": {"source_image_url": "https://cdn.example.com/grounded-key-art.jpg"},
        }
        shots = [f"https://shared.akamai.steamstatic.com/apps/9/ss_{i}.1920x1080.jpg" for i in range(3)]
        images = render_fallback.resolve_featured_images(
            "grounded",
            content_items=[selected],
            page_fetcher=lambda url: "",
            steam_resolver=lambda item: shots,
        )
        self.assertEqual(images, shots)

    def test_injected_page_fetcher_never_triggers_a_store_lookup(self):
        selected = {
            "source_id": "grounded",
            "title": "Grounded 2 – notes de mise à jour 0.5.1",
            "featured_image": {"source_image_url": "https://cdn.example.com/grounded-key-art.jpg"},
        }
        original = render_fallback.steam_screenshots_for_item
        render_fallback.steam_screenshots_for_item = lambda item: self.fail("network lookup")
        try:
            render_fallback.resolve_featured_images(
                "grounded",
                content_items=[selected],
                page_fetcher=lambda url: "",
                require_three=False,
            )
        finally:
            render_fallback.steam_screenshots_for_item = original

    def test_other_articles_cards_on_our_own_page_are_ignored(self):
        selected = {
            "source_id": "grounded",
            "title": "Grounded 2 – notes de mise à jour 0.5.1",
            "slug": "grounded-2-patch-notes",
        }
        other = {
            "source_id": "witcher",
            "title": "Patch Witcher 3 Remastered : ajustements",
            "slug": "patch-witcher-3-remastered",
        }
        page = """
        <img src="https://gamerquestfr.com/wp-content/uploads/2026/10/patch-witcher-3-remastered.jpg"
             alt="Grounded 2 à lire aussi">
        <img src="https://gamerquestfr.com/wp-content/uploads/2026/10/grounded-2-patch-notes-1024x576.jpg"
             alt="Grounded 2">
        <img src="https://cdn.example.com/grounded-2-screenshot.jpg" alt="Grounded 2 gameplay">
        """
        images = render_fallback.resolve_featured_images(
            "grounded",
            content_items=[selected, other],
            page_fetcher=lambda url: page,
            require_three=False,
        )
        self.assertEqual(images, ["https://cdn.example.com/grounded-2-screenshot.jpg"])

    def test_single_game_article_does_not_borrow_from_other_games(self):
        selected = {
            "source_id": "fire-emblem",
            "title": "Fire Emblem : Fortune’s Weave – date de sortie",
            "tags": ["Fire Emblem", "Nintendo", "Switch 2"],
        }
        mario = {
            "source_id": "mario",
            "title": "Mario Scream : date de sortie sur Switch 2",
            "tags": ["Mario", "Nintendo", "Switch 2", "Fire Emblem Direct"],
            "featured_image": {"source_image_url": "https://cdn.example.com/mario-scream.jpg"},
        }
        same_game = {
            "source_id": "fire-emblem-2",
            "title": "Fire Emblem Fortune’s Weave : nouveau trailer",
            "tags": ["Fire Emblem", "Nintendo"],
            "featured_image": {"source_image_url": "https://cdn.example.com/fe-trailer.jpg"},
        }
        images = render_fallback.resolve_featured_images(
            "fire-emblem",
            content_items=[selected, mario, same_game],
            page_fetcher=lambda url: "",
            require_three=False,
        )
        self.assertEqual(images, ["https://cdn.example.com/fe-trailer.jpg"])

    def test_roundup_only_borrows_from_games_it_names(self):
        roundup = {
            "source_id": "roundup",
            "title": "Les 7 meilleurs jeux similaires à Silksong pour patienter",
            "tags": ["Silksong", "Hollow Knight", "Nintendo", "recommandations"],
        }
        named = {
            "source_id": "silksong",
            "title": "Hollow Knight Silksong : date de sortie du DLC",
            "tags": ["Silksong", "Hollow Knight"],
            "featured_image": {"source_image_url": "https://cdn.example.com/silksong.jpg"},
        }
        unrelated = {
            "source_id": "pgw",
            "title": "Paris Games Week 2026 : le programme Nintendo et les recommandations",
            "tags": ["Paris Games Week", "Nintendo", "recommandations"],
            "featured_image": {"source_image_url": "https://cdn.example.com/paris-games-week.jpg"},
        }
        images = render_fallback.resolve_featured_images(
            "roundup",
            content_items=[roundup, named, unrelated],
            page_fetcher=lambda url: "",
            require_three=False,
        )
        self.assertEqual(images, ["https://cdn.example.com/silksong.jpg"])

    def test_images_needing_heavy_enlargement_are_rejected(self):
        urls = [f"https://cdn.example.com/{name}.jpg" for name in ("a", "b", "c", "d")]
        payloads = {
            urls[0]: _noise_image((1920, 1080), 1),
            # Passes the old 900x500 floor but needs 3.2x to fill a 1920px slide.
            urls[1]: _noise_image((1280, 600), 2),
            urls[2]: _noise_image((1920, 1080), 3),
            urls[3]: _noise_image((1600, 900), 4),
        }
        validated = render_fallback.validate_source_images(
            urls, image_fetcher=lambda url: payloads[url]
        )
        self.assertEqual(validated, [urls[0], urls[2], urls[3]])


if __name__ == "__main__":
    unittest.main()
