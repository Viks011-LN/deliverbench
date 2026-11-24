"""The drawdown control: cut the book when the NAV has fallen far enough from its high-water mark."""


def drawdown(nav, peak):
    """The fall from the high-water mark, as a negative fraction (0.0 at the peak)."""
    return nav / peak - 1.0


def drawdown_control(scale, current_drawdown, drawdown_limit, drawdown_scale):
    """The book's scale after the drawdown control: multiplied by drawdown_scale while the drawdown is at or
    beyond drawdown_limit; unchanged otherwise, or when there is no limit."""
    if drawdown_limit is not None and current_drawdown <= -drawdown_limit:
        scale = scale * drawdown_scale
    return scale
