import json
import unittest
from unittest.mock import patch

from social import idea_generator


def three_slides():
    return [
        {
            "title": "Hook",
            "body": "Short hook body",
            "visual_prompt": "Gaming image",
        },
        {
            "title": "Value",
            "body": "Supported useful information",
            "visual_prompt": "Gaming detail",
        },
        {
            "title": "Continue",
            "body": "Read the full story on GamerQuest.fr",
            "visual_prompt": "Gaming image with depth",
        },
    ]


class TestSocialAIRunner(unittest.TestCase):

    def test_prepare_content_for_ai_limits_items(self):
        content = []

        for index in range(20):
            content.append(
                {
                    "title": f"Article {index}",
                    "excerpt": "A" * 1000,
                    "source_type": "news",
                    "created_at": f"2026-09-{index + 1:02d}",
                }
            )

        result = idea_generator.prepare_content_for_ai(
            content
        )

        self.assertLessEqual(
            len(result),
            idea_generator.MAX_CONTENT_ITEMS,
        )

        for item in result:
            self.assertLessEqual(
                len(item["excerpt"]),
                idea_generator.MAX_EXCERPT_CHARS,
            )

    def test_parse_json_response_accepts_plain_json(self):
        raw = json.dumps(
            [
                {
                    "topic": "Topic",
                }
            ]
        )

        result = idea_generator.parse_json_response(
            raw
        )

        self.assertEqual(
            result[0]["topic"],
            "Topic",
        )

    def test_parse_json_response_accepts_fenced_json(self):
        raw = """```json
[
  {
    "topic": "Topic"
  }
]
```"""

        result = idea_generator.parse_json_response(
            raw
        )

        self.assertEqual(
            result[0]["topic"],
            "Topic",
        )

    @patch(
        "social.idea_generator.call_grok"
    )
    def test_generate_ideas_returns_three_concepts_max(
        self,
        mock_call,
    ):
        mock_call.return_value = json.dumps(
            [
                {
                    "topic": "A",
                    "angle": "A",
                    "format": "news",
                    "hook": "A",
                },
                {
                    "topic": "B",
                    "angle": "B",
                    "format": "ranking",
                    "hook": "B",
                },
                {
                    "topic": "C",
                    "angle": "C",
                    "format": "deal",
                    "hook": "C",
                },
                {
                    "topic": "D",
                    "angle": "D",
                    "format": "guide",
                    "hook": "D",
                },
            ]
        )

        result = idea_generator.generate_ideas(
            [
                {
                    "title": "Article",
                    "excerpt": "Facts",
                    "source_type": "news",
                }
            ]
        )

        self.assertEqual(
            len(result),
            3,
        )

    @patch(
        "social.idea_generator.call_grok"
    )
    def test_expand_idea_generates_complete_carousel_package(
        self,
        mock_call,
    ):
        mock_call.return_value = json.dumps(
            {
                "slides": three_slides(),
                "caption": "Caption",
                "cta": "Visit GamerQuest.fr",
                "hashtags": [
                    "#GamerQuest",
                    "#Gaming",
                ],
            }
        )

        result = idea_generator.expand_idea(
            {
                "topic": "Topic",
                "angle": "Angle",
                "format": "ranking",
                "hook": "Hook",
                "total_score": 82,
            },
            [
                {
                    "title": "Article",
                    "excerpt": "Facts",
                    "source_type": "news",
                }
            ],
        )

        self.assertEqual(
            len(result["slides"]),
            3,
        )

        self.assertEqual(
            result["total_score"],
            82,
        )

        self.assertEqual(
            result["caption"],
            "Caption",
        )

        self.assertEqual(
            result["cta"],
            "Visit GamerQuest.fr",
        )

    @patch(
        "social.idea_generator.call_grok"
    )
    def test_expand_idea_rejects_five_slides(
        self,
        mock_call,
    ):
        mock_call.return_value = json.dumps(
            {
                "slides": three_slides()
                + [
                    {
                        "title": "Extra 4",
                        "body": "Extra",
                        "visual_prompt": "",
                    },
                    {
                        "title": "Extra 5",
                        "body": "Extra",
                        "visual_prompt": "",
                    },
                ],
                "caption": "Caption",
                "cta": "CTA",
                "hashtags": [],
            }
        )

        with self.assertRaises(
            RuntimeError
        ):
            idea_generator.expand_idea(
                {
                    "topic": "Topic",
                    "angle": "Angle",
                    "format": "ranking",
                    "hook": "Hook",
                },
                [
                    {
                        "title": "Article",
                        "excerpt": "Facts",
                        "source_type": "news",
                    }
                ],
            )

    @patch(
        "social.idea_generator.call_grok"
    )
    def test_verify_carousel_accepts_valid_package(
        self,
        mock_call,
    ):
        mock_call.return_value = json.dumps(
            {
                "valid": True,
                "unsupported_claims": [],
                "reason": "",
            }
        )

        result = idea_generator.verify_carousel(
            {
                "topic": "Game",
                "hook": "Hook",
                "slides": three_slides(),
                "caption": "Caption",
                "cta": "CTA",
            },
            [
                {
                    "title": "Game",
                    "excerpt": "Supported fact",
                    "source_type": "news",
                }
            ],
        )

        self.assertTrue(
            result["valid"]
        )

        self.assertEqual(
            result["unsupported_claims"],
            [],
        )

    @patch(
        "social.idea_generator.call_grok"
    )
    def test_verify_carousel_reports_unsupported_claims(
        self,
        mock_call,
    ):
        mock_call.return_value = json.dumps(
            {
                "valid": False,
                "unsupported_claims": [
                    "Unsupported claim"
                ],
                "reason": "Not in source",
            }
        )

        result = idea_generator.verify_carousel(
            {
                "topic": "Game",
                "hook": "Hook",
                "slides": three_slides(),
                "caption": "Caption",
                "cta": "CTA",
            },
            [
                {
                    "title": "Game",
                    "excerpt": "Supported fact",
                    "source_type": "deal",
                }
            ],
        )

        self.assertFalse(
            result["valid"]
        )

        self.assertEqual(
            result["unsupported_claims"],
            [
                "Unsupported claim"
            ],
        )

    @patch(
        "social.idea_generator.call_grok"
    )
    def test_verify_prompt_allows_navigation_cta(
        self,
        mock_call,
    ):
        mock_call.return_value = json.dumps(
            {
                "valid": True,
                "unsupported_claims": [],
                "reason": "",
            }
        )

        idea_generator.verify_carousel(
            {
                "topic": "Game",
                "hook": "Hook",
                "slides": three_slides(),
                "caption": "Caption",
                "cta": (
                    "Lire la suite sur "
                    "GamerQuest.fr"
                ),
            },
            [
                {
                    "title": "Game",
                    "excerpt": (
                        "Le jeu sort le "
                        "8 avril 2027."
                    ),
                    "source_type": "news",
                }
            ],
        )

        prompt = mock_call.call_args[
            0
        ][0]

        self.assertIn(
            "A navigation CTA such as",
            prompt,
        )

        self.assertIn(
            "\"Lire la suite sur GamerQuest.fr\"",
            prompt,
        )

        self.assertIn(
            "is NOT a factual claim about the source",
            prompt,
        )

    @patch(
        "social.idea_generator.call_grok"
    )
    def test_repair_carousel_changes_only_package_fields(
        self,
        mock_call,
    ):
        repaired_slides = [
            {
                "title": "Hook",
                "body": "Supported fact",
                "visual_prompt": "Game image",
            },
            {
                "title": "Value",
                "body": "Supported fact",
                "visual_prompt": "Game detail",
            },
            {
                "title": "Continue",
                "body": "Read more on GamerQuest.fr",
                "visual_prompt": "Game image",
            },
        ]

        mock_call.return_value = json.dumps(
            {
                "slides": repaired_slides,
                "caption": "Fixed caption",
                "cta": "Visit GamerQuest.fr",
                "hashtags": [
                    "#GamerQuest"
                ],
            }
        )

        original = {
            "topic": "Game",
            "angle": "Angle",
            "format": "news",
            "hook": "Hook",
            "total_score": 80.5,
            "slides": three_slides(),
            "caption": "Original caption",
            "cta": "CTA",
            "hashtags": [
                "#Gaming"
            ],
        }

        fixed = idea_generator.repair_carousel(
            original,
            [
                {
                    "title": "Game",
                    "excerpt": "Supported fact",
                    "source_type": "deal",
                }
            ],
            [
                "Unsupported claim"
            ],
        )

        self.assertEqual(
            fixed["topic"],
            "Game",
        )

        self.assertEqual(
            fixed["total_score"],
            80.5,
        )

        self.assertEqual(
            len(fixed["slides"]),
            3,
        )

        self.assertEqual(
            fixed["slides"][0]["body"],
            "Supported fact",
        )

    @patch(
        "social.idea_generator.call_grok"
    )
    def test_repair_prompt_forbids_invented_hype(
        self,
        mock_call,
    ):
        mock_call.return_value = json.dumps(
            {
                "slides": three_slides(),
                "caption": "Caption",
                "cta": (
                    "Lire la suite sur "
                    "GamerQuest.fr"
                ),
                "hashtags": [
                    "#GamerQuest"
                ],
            }
        )

        idea_generator.repair_carousel(
            {
                "topic": "Game",
                "slides": three_slides(),
                "caption": "Caption",
                "cta": (
                    "Lire la suite sur "
                    "GamerQuest.fr"
                ),
                "hashtags": [],
            },
            [
                {
                    "title": "Game",
                    "excerpt": (
                        "Le trailer a été présenté "
                        "au State of Play."
                    ),
                    "source_type": "news",
                }
            ],
            [
                (
                    "Les fans sont très "
                    "enthousiastes."
                )
            ],
        )

        prompt = mock_call.call_args[
            0
        ][0]

        self.assertIn(
            "Do not invent audience reaction",
            prompt,
        )

        self.assertIn(
            "fan excitement",
            prompt,
        )

        self.assertIn(
            "hype",
            prompt,
        )

    @patch(
        "social.idea_generator.call_grok"
    )
    def test_repair_carousel_rejects_five_slides(
        self,
        mock_call,
    ):
        mock_call.return_value = json.dumps(
            {
                "slides": three_slides()
                + [
                    {
                        "title": "Extra",
                        "body": "Extra",
                        "visual_prompt": "",
                    },
                    {
                        "title": "Extra",
                        "body": "Extra",
                        "visual_prompt": "",
                    },
                ],
                "caption": "Caption",
                "cta": "CTA",
                "hashtags": [],
            }
        )

        with self.assertRaises(
            RuntimeError
        ):
            idea_generator.repair_carousel(
                {
                    "topic": "Game",
                    "slides": three_slides(),
                    "caption": "Caption",
                    "cta": "CTA",
                    "hashtags": [],
                },
                [
                    {
                        "title": "Game",
                        "excerpt": "Supported fact",
                        "source_type": "news",
                    }
                ],
                [
                    "Unsupported claim"
                ],
            )

    def test_build_expansion_prompt_requires_three_slides(
        self
    ):
        prompt = (
            idea_generator.build_expansion_prompt(
                {
                    "topic": "Topic",
                    "angle": "Angle",
                    "format": "news",
                    "hook": "Hook",
                },
                [
                    {
                        "title": "Article",
                        "excerpt": "Fact",
                        "source_type": "news",
                    }
                ],
            )
        )

        self.assertIn(
            "EXACTLY",
            prompt,
        )

        self.assertIn(
            "3 slides",
            prompt,
        )

    def test_repair_prompt_preserves_three_slide_structure(
        self
    ):
        prompt = idea_generator._safe_prompt(
            """
Preserve EXACTLY 3 slides.
Slide 1 = Hook
Slide 2 = Value
Slide 3 = Curiosity + traffic
"""
        )

        self.assertIn(
            "3 slides",
            prompt,
        )


if __name__ == "__main__":
    unittest.main()
