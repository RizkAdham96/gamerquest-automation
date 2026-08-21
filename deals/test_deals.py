from deals import should_accept_deal


def test_accepts_free_game():
    deal = {
        "title": "Example Game",
        "original_price": 59.99,
        "current_price": 0,
        "discount_percent": 100,
    }

    assert should_accept_deal(deal) is True


def test_accepts_90_percent_discount():
    deal = {
        "title": "Example Game",
        "original_price": 59.99,
        "current_price": 5.99,
        "discount_percent": 90,
    }

    assert should_accept_deal(deal) is True


def test_accepts_more_than_90_percent_discount():
    deal = {
        "title": "Example Game",
        "original_price": 59.99,
        "current_price": 2.99,
        "discount_percent": 95,
    }

    assert should_accept_deal(deal) is True


def test_rejects_89_percent_discount():
    deal = {
        "title": "Example Game",
        "original_price": 59.99,
        "current_price": 6.59,
        "discount_percent": 89,
    }

    assert should_accept_deal(deal) is False


def test_rejects_normal_discount():
    deal = {
        "title": "Example Game",
        "original_price": 59.99,
        "current_price": 29.99,
        "discount_percent": 50,
    }

    assert should_accept_deal(deal) is False
