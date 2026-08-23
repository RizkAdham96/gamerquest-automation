from pathlib import Path

from PIL import Image

from news_image_generator import generate_news_image


def test_generate_news_image_creates_1200x630_jpeg(tmp_path):
    output = tmp_path / "news.jpg"

    result = generate_news_image(
        title="Test Gaming News",
        source_image_url=None,
        output_path=output,
    )

    assert result.exists()

    image = Image.open(result)

    assert image.size == (1200, 630)
    assert image.format == "JPEG"
