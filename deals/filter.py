def should_accept_deal(deal):
    """Return True when a deal is genuinely worth surfacing to gamers.

    Rules are deliberately value-based rather than percentage-only:
    - free games always qualify
    - 80%+ discounts always qualify
    - 70-79% qualifies when the final price is <= 20 EUR
    - 60-69% qualifies only when the final price is <= 10 EUR
    - below 60% is ignored by this lightweight filter

    This keeps the feed useful without requiring paid APIs or AI calls.
    """

    current_price = float(deal.get("current_price") or 0)
    original_price = float(deal.get("original_price") or 0)
    discount_percent = float(deal.get("discount_percent") or 0)

    if current_price == 0:
        return True

    if discount_percent >= 80:
        return True

    # Strong mainstream-style discount: useful when the final ticket price
    # remains affordable for most players.
    if 70 <= discount_percent < 80:
        return current_price <= 20 and original_price > current_price

    # Lower percentage discounts only pass when the final price is truly low.
    if 60 <= discount_percent < 70:
        return current_price <= 10 and original_price > current_price

    return False
