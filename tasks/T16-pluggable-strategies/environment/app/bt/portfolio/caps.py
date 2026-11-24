"""The weight cap: no single name may carry more than max_weight of the NAV."""


def apply_weight_cap(weights, max_weight):
    """Cap each |weight| at max_weight and hand the excess to the uncapped names on the same side, in proportion to
    their weights, until nothing is over the cap. When every name on a side is at the cap, the rest of the excess
    is dropped (it stays in cash)."""
    capped = dict(weights)
    for side in (1.0, -1.0):
        names = [symbol for symbol in capped if capped[symbol] * side > 0.0]
        while True:
            excess = 0.0
            free = []
            for symbol in names:
                w = capped[symbol] * side
                if w > max_weight:
                    excess += w - max_weight
                    capped[symbol] = max_weight * side
                elif w < max_weight:
                    free.append(symbol)
            if excess == 0.0 or not free:
                break
            free_total = 0.0
            for symbol in free:
                free_total += capped[symbol] * side
            for symbol in free:
                capped[symbol] += side * excess * (capped[symbol] * side) / free_total
    return capped
