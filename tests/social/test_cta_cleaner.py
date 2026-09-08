import unittest

from social import render


class TestSocialCtaCleaner(unittest.TestCase):
    def test_removes_discover_more_gamerquest_sentence(self):
        text = (
            "Square Enix propose plusieurs éditions et a confirmé un premier DLC, "
            "détails à suivre. Découvrez plus sur GamerQuest.fr."
        )

        cleaned = render.remove_redundant_cta(text)

        self.assertEqual(
            cleaned,
            "Square Enix propose plusieurs éditions et a confirmé un premier DLC, détails à suivre.",
        )


if __name__ == "__main__":
    unittest.main()
