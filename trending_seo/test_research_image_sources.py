import unittest

import pipeline


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class FakePageClient:
    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        return self.pages.get(url, FakeResponse(404, ""))


class TestResearchImageSources(unittest.TestCase):
    def test_research_evidence_page_can_supply_featured_image(self):
        topic = {
            "topic": "The Witcher 3 Remastered",
            "sources": [
                {"url": "https://events.example/gamescom", "type": "official"},
            ],
        }
        research_context = {
            "usable_evidence": [
                {
                    "url": "https://publisher.example/witcher-3-remastered",
                    "title": "The Witcher 3 Remastered official page",
                }
            ]
        }
        client = FakePageClient({
            "https://events.example/gamescom": FakeResponse(
                200,
                "<title>Gamescom</title><meta property='og:image' content='/logo.jpg'>",
            ),
            "https://publisher.example/witcher-3-remastered": FakeResponse(
                200,
                """
                <title>The Witcher 3 Remastered</title>
                <meta property='og:title' content='The Witcher 3 Remastered'>
                <meta property='og:image' content='https://cdn.example/hash123.jpg'>
                <h1>The Witcher 3 Remastered</h1>
                """,
            ),
        })

        selected = pipeline.find_relevant_source_image(
            topic,
            research_context=research_context,
            client=client,
        )

        self.assertEqual(selected, "https://cdn.example/hash123.jpg")
        self.assertIn(
            "https://publisher.example/witcher-3-remastered",
            client.requested,
        )

    def test_duplicate_research_urls_are_deduplicated(self):
        topic = {
            "topic": "The Witcher 3 Remastered",
            "sources": [{"url": "https://publisher.example/page"}],
        }
        research_context = {
            "usable_evidence": [{"url": "https://publisher.example/page"}],
            "discovered_sources": [{"url": "https://publisher.example/page"}],
        }

        sources = pipeline.build_featured_image_sources(topic, research_context)

        self.assertEqual(
            [item["url"] for item in sources],
            ["https://publisher.example/page"],
        )

    def test_unrelated_research_page_still_cannot_supply_image(self):
        topic = {"topic": "The Witcher 3 Remastered", "sources": []}
        research_context = {
            "usable_evidence": [{"url": "https://publisher.example/other"}]
        }
        client = FakePageClient({
            "https://publisher.example/other": FakeResponse(
                200,
                "<title>Other game</title><meta property='og:image' content='https://cdn.example/hash.jpg'>",
            )
        })

        selected = pipeline.find_relevant_source_image(
            topic,
            research_context=research_context,
            client=client,
        )

        self.assertEqual(selected, "")


if __name__ == "__main__":
    unittest.main()
