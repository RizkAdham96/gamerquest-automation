from deals.filter import should_accept_deal


def test_accepts_free_games():
    assert should_accept_deal({"current_price": 0, "discount_percent": 0}) is True


def test_accepts_80_percent_or_more_automatically():
    assert should_accept_deal({"original_price": 49.99, "current_price": 9.99, "discount_percent": 80}) is True
    assert should_accept_deal({"original_price": 59.99, "current_price": 5.99, "discount_percent": 90}) is True


def test_accepts_strong_70_percent_value_deal():
    assert should_accept_deal({"original_price": 59.99, "current_price": 17.99, "discount_percent": 70}) is True


def test_rejects_expensive_70_percent_deal():
    assert should_accept_deal({"original_price": 99.99, "current_price": 29.99, "discount_percent": 70}) is False


def test_accepts_60_to_69_only_when_final_price_is_exceptional():
    assert should_accept_deal({"original_price": 29.99, "current_price": 9.99, "discount_percent": 67}) is True
    assert should_accept_deal({"original_price": 49.99, "current_price": 19.99, "discount_percent": 60}) is False


def test_rejects_below_60_percent_even_if_cheap():
    assert should_accept_deal({"original_price": 9.99, "current_price": 4.99, "discount_percent": 50}) is False
