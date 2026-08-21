def should_accept_deal(deal):
    """
    Accept a deal when:
    - the game is free
    - OR the discount is 90% or higher
    """

    current_price = deal.get("current_price")
    discount_percent = deal.get("discount_percent", 0)

    if current_price == 0:
        return True

    if discount_percent >= 90:
        return True

    return False
