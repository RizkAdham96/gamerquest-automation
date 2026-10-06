import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import evergreen_topics
import pipeline
import scorer
from groq_budget import DEFAULT_TPM_CEILING, estimate_request_tokens
from seo_engine import build_seo_brief, classify_evergreen_intent, select_seo_candidates


def steam_details(appid=1245620, name="ELDEN RING"):
    return {
        "type": "game",
        "steam_appid": appid,
        "name": name,
        "developers": ["FromSoftware, Inc."],
        "publishers": ["Bandai Namco Entertainment"],
        "release_date": {"coming_soon": False, "date": "24 févr. 2022"},
        "genres": [{"description": "Action"}, {"description": "RPG"}],
        "platforms": {"windows": True, "mac": False, "linux": False},
        "controller_support": "full",
        "short_description": "Levez-vous, Sans-éclat.",
        "categories": [
            {"description": "Solo"},
            {"description": "Coopération en ligne"},
        ],
        "pc_requirements": {
            "minimum": (
                "<strong>Minimale :</strong><br><ul><li><strong>Processeur :</strong> "
                "INTEL CORE I5-8400<br></li><li><strong>Mémoire vive :</strong> 12 GB"
                "<br></li><li><strong>Graphiques :</strong> GTX 1060 3 GB</li></ul>"
            ),
            "recommended": (
                "<strong>Recommandée :</strong><br><ul><li><strong>Mémoire vive :"
                "</strong> 16 GB de mémoire</li></ul>"
            ),
        },
        "screenshots": [{"path_full": "https://cdn.example/elden/shot1.jpg"}],
        "header_image": "https://cdn.example/elden/header.jpg",
    }


def discover(games, known=None, checked=None, details=steam_details, search=None):
    calls = []

    def default_search(name):
        calls.append(name)
        return {"id": 1245620, "name": name}

    topics = evergreen_topics.discover_evergreen_topics(
        known if known is not None else set(),
        checked if checked is not None else set(),
        games=games,
        search=search or default_search,
        fetch_details=lambda appid: details(),
    )
    return topics, calls


class TestEvergreenTopics(unittest.TestCase):
    def test_game_yields_config_and_multiplayer_topics_with_store_facts(self):
        topics, _ = discover(["Elden Ring"])
        self.assertEqual(
            [topic["keywords"][0] for topic in topics],
            ["configuration pc Elden Ring", "Elden Ring multijoueur"],
        )
        config, multi = topics
        self.assertEqual(config["id"], "evg-config-1245620")
        evidence = config["sources"][0]["evidence"]
        self.assertIn("INTEL CORE I5-8400", evidence)
        self.assertIn("16 GB de mémoire", evidence)
        self.assertNotIn("<", evidence)
        self.assertIn("Coopération en ligne", multi["sources"][0]["evidence"])
        self.assertEqual(
            config["sources"][0]["image_url"], "https://cdn.example/elden/shot1.jpg"
        )

    def test_generated_topics_reach_the_write_threshold(self):
        topics, _ = discover(["Elden Ring"])
        scored_topics = [scorer.analyze_topic_locally(topic) for topic in topics]
        for scored in scored_topics:
            self.assertEqual(scored["decision"], "WRITE", scored["topic"])
            self.assertTrue(classify_evergreen_intent(scored)["eligible"])
        selected = select_seo_candidates(
            {"topics": scored_topics}, max_articles=2, history={"published": []}
        )
        self.assertEqual(len(selected), 2)

    def test_checked_games_are_never_looked_up_again(self):
        checked = set()
        _, first_calls = discover(["Elden Ring"], checked=checked)
        topics, second_calls = discover(["Elden Ring", "Hades"], checked=checked)
        self.assertEqual(first_calls, ["Elden Ring"])
        self.assertEqual(second_calls, ["Hades"])
        self.assertEqual(len(topics), 2)

    def test_unmatched_games_do_not_starve_later_games(self):
        checked = set()
        bundles = [f"Bundle {index}" for index in range(6)]

        def search(name):
            return None if name.startswith("Bundle") else {"id": 1245620}

        first, _ = discover(bundles + ["Elden Ring"], checked=checked, search=search)
        second, _ = discover(bundles + ["Elden Ring"], checked=checked, search=search)
        self.assertEqual(first, [])
        self.assertEqual(len(second), 2)

    def test_non_games_and_missing_store_data_are_skipped(self):
        topics, _ = discover(["Elden Ring"], details=lambda: {**steam_details(), "type": "dlc"})
        self.assertEqual(topics, [])
        topics, _ = discover(
            ["Elden Ring"],
            details=lambda: {**steam_details(), "pc_requirements": [], "categories": []},
        )
        self.assertEqual(topics, [])

    def test_lookup_failure_is_retried_on_a_later_run(self):
        checked = set()

        def failing(name):
            raise RuntimeError("steam down")

        topics, _ = discover(["Elden Ring"], checked=checked, search=failing)
        self.assertEqual(topics, [])
        self.assertEqual(checked, set())


class TestStoreTopicPipeline(unittest.TestCase):
    def topic(self):
        return evergreen_topics.build_game_topics("Elden Ring", steam_details())[0]

    def test_store_topic_skips_researcher_and_keeps_full_evidence(self):
        with patch.object(
            pipeline.researcher,
            "build_research_record",
            side_effect=AssertionError("researcher must not run for store topics"),
        ):
            context = pipeline.build_research_context(self.topic())
        self.assertTrue(pipeline.research_context_is_sufficient(context))
        compact = pipeline.compact_research_context(context)
        self.assertIn("16 GB de mémoire", compact["sources"][0]["text"])

    def test_publisher_topic_still_uses_researcher(self):
        topic = {
            "id": "rss-1",
            "topic": "x",
            "sources": [{"url": "https://example.com", "evidence": "y" * 200}],
        }
        with patch.object(
            pipeline.researcher,
            "build_research_record",
            return_value={"usable_evidence": [{"url": "u"}]},
        ) as record:
            pipeline.build_research_context(topic)
        record.assert_called_once()

    def test_store_topic_uses_official_artwork_without_fetching(self):
        class NoNetwork:
            def get(self, *args, **kwargs):
                raise AssertionError("no page fetch expected")

        image = pipeline.find_relevant_source_image(self.topic(), client=NoNetwork())
        self.assertEqual(image, "https://cdn.example/elden/shot1.jpg")

    def test_store_topics_are_filed_under_guides(self):
        for keyword in ("configuration pc Elden Ring", "Elden Ring multijoueur"):
            self.assertEqual(
                pipeline.wordpress_category_ids_for_brief(
                    {"primary_keyword": keyword, "search_intent": "information"}
                ),
                [3],
            )

    def test_article_request_fits_the_tpm_safety_ceiling(self):
        details = steam_details()
        long_requirements = "<li><strong>Processeur :</strong> INTEL CORE I7-8700K</li>" * 60
        details["pc_requirements"] = {
            "minimum": long_requirements,
            "recommended": long_requirements,
        }
        topic = evergreen_topics.build_game_topics("Elden Ring", details)[0]
        scored = scorer.analyze_topic_locally(topic)
        prompt = pipeline.build_article_prompt(
            build_seo_brief(scored),
            research_context=pipeline.build_research_context(scored),
        )
        estimate = estimate_request_tokens(
            [
                {"role": "system", "content": "x" * 80},
                {"role": "user", "content": prompt},
            ],
            pipeline.SEO_ARTICLE_MAX_TOKENS,
        )
        self.assertLessEqual(estimate, DEFAULT_TPM_CEILING)


class TestArticleGenerationRoom(unittest.TestCase):
    def test_article_call_limits_reasoning_and_allows_a_full_article(self):
        captured = {}

        class Completions:
            def create(self, **kwargs):
                captured.update(kwargs)
                raise RuntimeError("stop after capturing the request")

        class FakeGroq:
            def __init__(self, **kwargs):
                self.chat = type("Chat", (), {"completions": Completions()})()

        topic = evergreen_topics.build_game_topics("Elden Ring", steam_details())[0]
        scored = scorer.analyze_topic_locally(topic)
        with patch.object(pipeline, "Groq", FakeGroq), patch.object(
            pipeline, "consume_run_budget", lambda *args, **kwargs: 0
        ), patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            pipeline.generate_seo_article(
                build_seo_brief(scored),
                research_context=pipeline.build_research_context(scored),
            )
        self.assertEqual(captured["extra_body"], {"reasoning_effort": "low"})
        self.assertGreaterEqual(captured["max_tokens"], 3500)


class TestScorerOrdering(unittest.TestCase):
    def test_evergreen_topics_are_scored_before_the_feed_backlog(self):
        backlog = [
            {
                "id": f"rss-{index}",
                "topic": f"Headline number {index}",
                "status": "new",
                "region": "FR",
                "keywords": [f"Headline number {index}"],
                "sources": [],
            }
            for index in range(20)
        ]
        evergreen = evergreen_topics.build_game_topics("Elden Ring", steam_details())
        with tempfile.TemporaryDirectory() as directory:
            intel = Path(directory) / "topics.json"
            scored = Path(directory) / "scored.json"
            intel.write_text(
                json.dumps({"topics": backlog + evergreen}), encoding="utf-8"
            )
            with patch.object(scorer, "INTEL_FILE", intel), patch.object(
                scorer, "SCORED_FILE", scored
            ):
                scorer.main()
            saved = json.loads(scored.read_text(encoding="utf-8"))["topics"]
        self.assertEqual(
            [item["id"] for item in saved[:2]],
            ["evg-config-1245620", "evg-multi-1245620"],
        )


if __name__ == "__main__":
    unittest.main()
