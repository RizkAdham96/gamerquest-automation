import image_fallbacks as fb


def test_youtube_ids():
    assert fb.youtube_video_id("https://www.youtube.com/watch?v=kKfb9ox_c9Y") == "kKfb9ox_c9Y"
    assert fb.youtube_video_id("https://youtu.be/kKfb9ox_c9Y?t=3") == "kKfb9ox_c9Y"
    assert fb.youtube_video_id("https://www.youtube.com/shorts/kKfb9ox_c9Y") == "kKfb9ox_c9Y"
    assert fb.youtube_video_id("https://www.ign.com/watch?v=kKfb9ox_c9Y") == ""
    assert fb.youtube_thumbnail_candidates("https://www.youtube.com/watch?v=kKfb9ox_c9Y")[0].endswith(
        "/kKfb9ox_c9Y/maxresdefault.jpg"
    )


def test_game_name_from_title():
    assert fb.game_name_from_title("Neon Abyss 2 : date de sortie, plateformes") == "Neon Abyss 2"
    assert fb.game_name_from_title("Crossplay The Division 2 – date") == "Crossplay The Division 2"


def test_steam_name_matching_is_strict():
    assert fb.steam_name_matches("Neon Abyss 2", "Neon Abyss 2")
    assert fb.steam_name_matches("Hades II", "Hades II")
    assert not fb.steam_name_matches("Neon Abyss 2", "Neon Abyss")
    assert not fb.steam_name_matches("Hades", "Hades II")
    assert not fb.steam_name_matches("Dates de sortie", "Date Night")
    assert not fb.steam_name_matches("", "Anything")


class FakeResp:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSession:
    def get(self, url, params=None, headers=None, timeout=None):
        if "storesearch" in url:
            return FakeResp({"items": [{"id": 10, "name": "Neon Abyss"}, {"id": 20, "name": "Neon Abyss 2"}]})
        return FakeResp({"20": {"data": {"screenshots": [{"path_full": "https://x/shot.jpg"}]}}})


def test_steam_artwork_picks_exact_game():
    urls = fb.steam_artwork_candidates("Neon Abyss 2 : date de sortie", session=FakeSession())
    assert urls[0].endswith("/apps/20/library_hero.jpg")
    assert "https://x/shot.jpg" in urls


def test_refresh_replaces_only_blank_images(tmp_path):
    from PIL import Image
    from scripts import refresh_blank_news_images as refresh
    import news_image_generator as gen

    gen.create_fallback_background().save(tmp_path / "blank.jpg")
    art = Image.new("RGB", (1280, 720))
    for x in range(0, 1280, 40):
        art.paste((255, 255, 255), (x, 0, x + 20, 720))
    gen.cover_image(art).save(tmp_path / "real.jpg")

    refresh.download_source_image = lambda url: art
    find = lambda article: ["https://img.youtube.com/vi/x/maxresdefault.jpg"]

    blank = {"featured_image": {"filename": "blank.jpg"}}
    real = {"featured_image": {"filename": "real.jpg"}}
    assert refresh.refresh_article_image(blank, tmp_path, find)
    assert not gen.image_is_blank(Image.open(tmp_path / "blank.jpg"))
    assert refresh.refresh_article_image(real, tmp_path, find) == ""
