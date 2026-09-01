import unittest

import pipeline


class TestSeoPipelinePublishMode(unittest.TestCase):

    def test_seo_pipeline_is_configured_for_public_publish(self):
        self.assertEqual(
            pipeline.WORDPRESS_STATUS,
            "publish",
        )


if __name__ == "__main__":
    unittest.main()
