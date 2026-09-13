import unittest

from deals.publish_wordpress import deal_category_slugs


class DealWordPressCategoryTests(unittest.TestCase):
    def test_all_deals_are_in_bons_plans(self):
        article = {"deal": {"current_price": 17.99, "discount_percent": 70}}
        self.assertIn("bons-plans", deal_category_slugs(article))

    def test_free_deals_also_keep_jeux_gratuits(self):
        article = {"deal": {"current_price": 0, "discount_percent": 100}}
        self.assertEqual(["bons-plans", "jeux-gratuits"], deal_category_slugs(article))


if __name__ == "__main__":
    unittest.main()
