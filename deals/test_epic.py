from deals.epic import is_valid_epic_free_game


def test_accepts_paid_game_that_becomes_free():
    game = {
        "title": "Cardpocalypse Standard Edition",
        "original_price": 23.99,
        "current_price": 0,
    }

    assert is_valid_epic_free_game(game) is True


def test_rejects_already_free_item():
    game = {
        "title": "Pack de Mage Épique",
        "original_price": 0,
        "current_price": 0,
    }

    assert is_valid_epic_free_game(game) is False


def test_rejects_non_free_item():
    game = {
        "title": "Example Game",
        "original_price": 39.99,
        "current_price": 9.99,
    }

    assert is_valid_epic_free_game(game) is False
