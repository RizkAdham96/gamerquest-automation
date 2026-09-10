from deals.filter import should_accept_deal


def test_accepts_free_games():
    assert should_accept_deal({"current_price": 0, "discount_percent": 0}) is True


def test_accepts_exactly_80_percent_discount():
    assert should_accept_deal({"current_price": 9.99, "discount_percent": 80}) is True


def test_accepts_more_than_80_percent_discount():
    assert should_accept_deal({"current_price": 4.99, "discount_percent": 85}) is True


def test_rejects_below_80_percent_discount():
    assert should_accept_deal({"current_price": 9.99, "discount_percent": 79}) is False
