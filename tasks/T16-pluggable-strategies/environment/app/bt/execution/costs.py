"""Trading costs: commission and slippage, in basis points of the traded notional."""
from bt.constants import BPS


def commission(notional, commission_bps, min_commission):
    """The commission on a trade of this notional, at least min_commission."""
    fee = notional * commission_bps / BPS
    if fee < min_commission:
        fee = min_commission
    return fee


def slippage(notional, slippage_bps):
    """The slippage on a trade of this notional."""
    return notional * slippage_bps / BPS


def trade_cost(notional, config):
    """(commission, slippage) on a trade of this notional, under the config's cost settings."""
    fee = commission(notional, config["commission_bps"], config["min_commission"])
    slip = slippage(notional, config["slippage_bps"])
    return fee, slip
