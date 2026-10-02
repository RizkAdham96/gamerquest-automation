import unittest
from social import meta_publisher


class Response:
    status_code = 200
    def __init__(self, payload):
        self.payload = payload
    def json(self):
        return self.payload


class API:
    def __init__(self, payload):
        self.payload = payload
    def get(self, url, params=None, timeout=None):
        if not url.endswith('/ig-post-123') or params.get('access_token') != 'test-token':
            raise AssertionError('Wrong media or credentials requested')
        return Response(self.payload)


class PublicationVerificationTests(unittest.TestCase):
    def payload(self):
        return {'id': 'ig-post-123', 'media_type': 'CAROUSEL_ALBUM',
                'permalink': 'https://www.instagram.com/p/verified/',
                'children': {'data': [{'id': '1'}, {'id': '2'}, {'id': '3'}]}}

    def test_returns_permalink_only_after_meta_confirms_three_slide_carousel(self):
        result = meta_publisher.verify_instagram_carousel(
            'ig-post-123', 'test-token', requests_module=API(self.payload()))
        self.assertEqual(result['permalink'], 'https://www.instagram.com/p/verified/')
        self.assertEqual(result['child_count'], 3)

    def test_rejects_unconfirmed_or_wrong_post(self):
        for changes in ({'id': 'wrong'}, {'media_type': 'IMAGE'}, {'permalink': ''},
                        {'children': {'data': [{'id': '1'}, {'id': '2'}]}},
                        {'children': {'data': [{'id': '1'}] * 3}}):
            payload = {**self.payload(), **changes}
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                meta_publisher.verify_instagram_carousel(
                    'ig-post-123', 'test-token', requests_module=API(payload))


if __name__ == '__main__':
    unittest.main()
