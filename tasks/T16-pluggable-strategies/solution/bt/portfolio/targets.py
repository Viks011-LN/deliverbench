"""Target positions: from a weight of the NAV to a number of units."""


def target_units(weight, scale, nav, price):
    """Units to hold for `weight` of the NAV at `price`, after the book's scale (volatility and drawdown)."""
    return weight * scale * nav / price
