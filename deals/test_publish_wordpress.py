from datetime import datetime, timezone

from deals.publish_wordpress import is_expired


def test_expired_deal_is_rejected_before_wordpress_publish():
    article = {"deal": {"expires_at": "2026-09-10T15:00:00.000Z"}}
    now = datetime(2026, 9, 10, 15, 0, 1, tzinfo=timezone.utc)

    assert is_expired(article, now=now) is True


def test_future_deal_remains_publishable():
    article = {"deal": {"expires_at": "2026-09-10T15:00:00.000Z"}}
    now = datetime(2026, 9, 10, 14, 59, 59, tzinfo=timezone.utc)

    assert is_expired(article, now=now) is False


def test_deal_without_expiry_remains_publishable():
    assert is_expired({"deal": {}}, now=datetime.now(timezone.utc)) is False
