"""From scores to weights: the exclusion list, the minimum history and the price floor, then the ranking."""


def apply_exclusions(scores, exclude):
    """Leave out of the ranking (score None) every stock on the exclusion list. Names on the list that the price
    file does not have are ignored."""
    if not exclude:
        return scores
    return {symbol: None if symbol in exclude else score for symbol, score in scores.items()}


def apply_min_history(scores, first_prices, t, min_history):
    """Leave out of the ranking every stock with fewer than min_history prices on day t, counted from its first
    price in the run (today's included). first_prices maps each symbol to the index of its first price, or None."""
    if min_history <= 1:
        return scores
    kept = {}
    for symbol, score in scores.items():
        first = first_prices[symbol]
        if score is not None and (first is None or t - first + 1 < min_history):
            kept[symbol] = None
        else:
            kept[symbol] = score
    return kept


def apply_price_floor(scores, prices_today, min_price):
    """Leave out of the ranking (score None) every stock whose price today is below min_price. A min_price of 0
    (the default) leaves every score as it is."""
    if min_price <= 0.0:
        return scores
    floored = {}
    for symbol, score in scores.items():
        price = prices_today[symbol]
        if score is not None and price is not None and price < min_price:
            floored[symbol] = None
        else:
            floored[symbol] = score
    return floored


def ranked(scores):
    """(score, symbol) for every scored stock, best first; ties are broken by symbol, so the result never depends
    on dictionary order."""
    return sorted(((score, symbol) for symbol, score in scores.items() if score is not None),
                  key=lambda pair: (-pair[0], pair[1]))


def scores_to_weights(scores, top_n, allow_short):
    """Long the top_n positive scores and, if shorting is allowed, short the top_n most negative ones, each book
    weighted in proportion to the scores. A long-only book adds up to 1; a long-short book has 0.5 on each side.
    A score of 0 is neither long nor short."""
    order = ranked(scores)
    longs = [pair for pair in order if pair[0] > 0.0][:top_n]
    shorts = []
    if allow_short:
        shorts = [pair for pair in reversed(order) if pair[0] < 0.0][:top_n]
    book = 0.5 if allow_short else 1.0
    weights = {}
    if longs:
        total = sum(score for score, _ in longs)
        for score, symbol in longs:
            weights[symbol] = book * score / total
    if shorts:
        total = sum(-score for score, _ in shorts)
        for score, symbol in shorts:
            weights[symbol] = book * score / total
    return weights
