from deals.steam import fetch_steam_specials


def test_steam_returns_list():
    deals = fetch_steam_specials()

    assert isinstance(deals, list)


def test_steam_deals_have_required_fields():
    deals = fetch_steam_specials()

    if not deals:
        return

    deal = deals[0]

    assert "title" in deal
    assert "store" in deal
    assert "original_price" in deal
    assert "current_price" in deal
    assert "discount_percent" in deal
    assert "url" in deal
