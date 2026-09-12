import unittest

from platform_classifier import classify_platforms, merge_platform_tags


class PlatformClassifierTests(unittest.TestCase):
    def test_classifies_nintendo_playstation_and_xbox_from_article_text(self):
        text = (
            "Professor Layton arrives on Nintendo Switch 2, "
            "PS5 and Xbox Series X|S."
        )

        self.assertEqual(
            classify_platforms(text),
            ["Nintendo", "PlayStation", "Xbox"],
        )

    def test_does_not_false_positive_xbox_from_generic_microsoft_reference(self):
        self.assertEqual(
            classify_platforms("Microsoft Windows PC release on Steam"),
            [],
        )

    def test_merges_platform_tags_without_duplicates(self):
        self.assertEqual(
            merge_platform_tags(
                ["Switch 2", "Nintendo"],
                ["Nintendo"],
            ),
            ["Switch 2", "Nintendo"],
        )


if __name__ == "__main__":
    unittest.main()
