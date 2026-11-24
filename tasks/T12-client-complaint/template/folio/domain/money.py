"""Money: a Decimal amount with an ISO currency code.

Amounts in different currencies never mix silently: ``Money("10", "GBP") +
Money("10", "USD")`` raises CurrencyMismatch. Convert one side first with
FxRates.convert(). Rounding happens only at the edges (display and export),
never in the middle of a calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Iterable, Union

Number = Union[Decimal, int]

# Currencies whose minor unit is not two decimal places.
_MINOR_UNITS = {"JPY": 0, "KRW": 0, "BHD": 3, "KWD": 3}


class CurrencyMismatch(ValueError):
    """An operation combined amounts in two different currencies."""

    def __init__(self, left: str, right: str, operation: str):
        self.left = left
        self.right = right
        super().__init__(f"cannot {operation} {left} and {right} amounts; convert one side first")


def check_currency(code) -> str:
    """Return ``code`` if it looks like an ISO 4217 code, else raise ValueError."""
    if not (isinstance(code, str) and len(code) == 3 and code.isascii() and code.isalpha() and code.isupper()):
        raise ValueError(f"invalid currency code {code!r}: expected three upper-case letters such as 'GBP'")
    return code


def to_decimal(value, what: str = "amount") -> Decimal:
    """Convert ``value`` to a finite Decimal.

    Floats go through repr() so that 0.1 becomes Decimal('0.1') rather than
    the nearest binary fraction. Booleans are refused even though Python
    treats them as ints: a ``true`` where a number belongs is always a typo.
    """
    if isinstance(value, bool):
        raise TypeError(f"{what} must be a number, not a boolean")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(repr(value))
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except InvalidOperation:
            raise ValueError(f"{what} {value!r} is not a number") from None
    else:
        raise TypeError(f"{what} must be a number, not {type(value).__name__}")
    if not result.is_finite():
        raise ValueError(f"{what} must be a finite number, got {value!r}")
    return result


def minor_units(currency: str) -> int:
    """Decimal places of the currency's minor unit (2 unless listed above)."""
    return _MINOR_UNITS.get(currency, 2)


def quantize(amount: Decimal, places: int) -> Decimal:
    """Round half-even to ``places`` decimal places."""
    return amount.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, slots=True)
class Money:
    """An immutable amount of one currency. See the module docstring for the rules."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", to_decimal(self.amount))
        check_currency(self.currency)

    @classmethod
    def zero(cls, currency: str) -> "Money":
        return cls(Decimal(0), currency)

    def _require_same(self, other: "Money", operation: str) -> None:
        if other.currency != self.currency:
            raise CurrencyMismatch(self.currency, other.currency, operation)

    def __add__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same(other, "add")
        return Money(self.amount + other.amount, self.currency)

    def __radd__(self, other):
        # Lets the built-in sum() start from its default 0.
        if other == 0:
            return self
        return NotImplemented

    def __sub__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same(other, "subtract")
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __mul__(self, factor: Number):
        if isinstance(factor, Money):
            raise TypeError("cannot multiply two Money amounts")
        if isinstance(factor, (Decimal, int)) and not isinstance(factor, bool):
            return Money(self.amount * factor, self.currency)
        return NotImplemented

    __rmul__ = __mul__

    def __truediv__(self, other):
        """``Money / Money`` gives a Decimal ratio; ``Money / number`` gives Money."""
        if isinstance(other, Money):
            self._require_same(other, "divide")
            if other.amount == 0:
                raise ZeroDivisionError(f"cannot divide by a zero {other.currency} amount")
            return self.amount / other.amount
        if isinstance(other, (Decimal, int)) and not isinstance(other, bool):
            return Money(self.amount / other, self.currency)
        return NotImplemented

    def __lt__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same(other, "compare")
        return self.amount < other.amount

    def __le__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same(other, "compare")
        return self.amount <= other.amount

    def is_zero(self) -> bool:
        return self.amount == 0

    def rounded(self, places: int | None = None) -> "Money":
        """Round to ``places`` decimals, or to the currency's minor unit."""
        if places is None:
            places = minor_units(self.currency)
        return Money(quantize(self.amount, places), self.currency)

    def __str__(self) -> str:
        places = minor_units(self.currency)
        return f"{self.currency} {quantize(self.amount, places):,.{places}f}"


def sum_money(amounts: Iterable[Money], currency: str) -> Money:
    """Add up ``amounts``, which must all be in ``currency``. Empty gives zero."""
    total = Money.zero(currency)
    for amount in amounts:
        total = total + amount
    return total
