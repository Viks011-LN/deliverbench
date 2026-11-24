"""Measure how far each reading of the standard moves T11's answers (docs/job-plans/T11-TICKLIST.md).

Each variant is the reference solution (solution/cdslib) with one choice changed: an open detail read another way,
or a lure. It is run on every hidden case (tests/data/cases.json, ISDA's answers) and the largest errors are
printed per check, in basis points and dollars, with the number of cases outside the check's tolerance.
Needs no ISDA library. Run: python isda/measure.py [variant ...]
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import io
import importlib
import json
import math
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE / "solution"))
CASES = json.loads((HERE / "tests" / "data" / "cases.json").read_text(encoding="utf-8"))
TIE_OUTS = list(csv.DictReader(io.StringIO((HERE / "environment" / "app" / "data" / "tie-outs.csv").read_text())))
D = dt.date.fromisoformat
TMP = Path(tempfile.mkdtemp())
for rel, text in CASES["files"].items():
    (TMP / rel).parent.mkdir(parents=True, exist_ok=True)
    (TMP / rel).write_text(text, encoding="utf-8")


def fresh():
    """A fresh copy of the reference solution's modules (each variant patches its own)."""
    for name in [m for m in sys.modules if m == "cdslib" or m.startswith("cdslib.")]:
        del sys.modules[name]
    lib = importlib.import_module("cdslib")
    lib.dates.HOLIDAYS_FILE = TMP / "data" / "holidays.csv"
    return lib


# ----- the variants ------------------------------------------------------------------------------------------

def no_half_day(lib):
    lib.legs.HALF_DAY = 0.0


def no_series(lib):
    lib.legs.SERIES_THRESHOLD = -1.0


def always_series(lib):
    lib.legs.SERIES_THRESHOLD = 1e9


def benchmark_from_step_in(lib):
    """The quoting convention's flat curve fitted to a contract accruing from the step-in date."""
    pricing = lib.pricing
    original = pricing.flat_curve

    def flat_curve(trade_date, maturity, spread, recovery, discount):
        contract = pricing.Contract.make(trade_date, maturity)
        dates = contract.dates
        start = dates.step_in
        periods = [p for p in contract.periods if p.accrual_end > start]
        first = periods[0]
        periods[0] = lib.dates.Period(start, first.accrual_end, first.pay_date, first.amount)
        bench = pricing.Contract(dates, maturity, periods)

        def value(h):
            return bench.clean_value(spread, recovery, discount, lib.curves.CreditCurve(trade_date, [maturity], [h]))

        hi = 1.0
        while value(hi) < 0:
            hi *= 2
        return lib.curves.CreditCurve(trade_date, [maturity], [pricing.solve(value, 0.0, hi)])

    pricing.flat_curve = flat_curve
    assert original


def par_at_step_in(lib):
    """ISDA's own par spread function: the clean fee leg valued at the step-in date."""
    contract_cls = lib.pricing.Contract

    def par_spread(self, recovery, discount, credit):
        protection, premium, accrued = self.legs(1.0, recovery, discount, credit)
        grow = discount.discount_factor(self.dates.cash_settle) / discount.discount_factor(self.dates.step_in)
        return protection * grow / (premium * grow - accrued)

    contract_cls.par_spread = par_spread


def accrual_from_end_of_first_day(lib):
    """Accrued time at default measured from the end of the period's first day (no start-of-day shift)."""
    legs = lib.legs
    original = legs.accrued_on_default

    def shifted(period, coupon, step_in_day, discount, credit, trade):
        moved = lib.dates.Period(period.accrual_start + dt.timedelta(days=1), period.accrual_end + dt.timedelta(days=1),
                                 period.pay_date, period.amount)
        return original(moved, coupon, step_in_day + 1, discount, credit, trade)

    legs.accrued_on_default = shifted


def survive_to_pay_date(lib):
    legs = lib.legs

    def premium_leg(dates, periods, coupon, discount, credit):
        trade = dates.trade_date
        total = 0.0
        for period in periods:
            if period.accrual_end <= dates.step_in:
                continue
            amount = coupon * (period.accrual_end - period.accrual_start).days / 360
            total += amount * credit.survival(period.pay_date) * discount.discount_factor(period.pay_date)
            total += legs.accrued_on_default(period, coupon, (dates.step_in - trade).days, discount, credit, trade)
        return total

    legs.premium_leg = premium_leg
    lib.pricing.premium_leg = premium_leg


def protection_from_end_of_step_in(lib):
    legs = lib.legs
    original = legs.protection_leg

    def protection_leg(dates, maturity_day, recovery, discount, credit):
        full = original(dates, maturity_day, recovery, discount, credit)
        first_day = original(dates, 1, recovery, discount, credit)
        return full - first_day

    lib.pricing.protection_leg = protection_leg


def value_at_trade_date(lib):
    contract_cls = lib.pricing.Contract
    original = contract_cls.legs

    def legs(self, coupon, recovery, discount, credit):
        protection, premium, accrued = original(self, coupon, recovery, discount, credit)
        grow = discount.discount_factor(self.dates.cash_settle)
        return protection * grow, premium * grow, accrued

    contract_cls.legs = legs


def no_extra_day_at_maturity(lib):
    dates = lib.dates
    original = dates.payment_schedule

    def payment_schedule(trade_date, maturity, coupon_bp, notional):
        periods = original(trade_date, maturity, coupon_bp, notional)
        last = periods[-1]
        end = last.accrual_end - dt.timedelta(days=1)
        periods[-1] = dates.Period(last.accrual_start, end, last.pay_date,
                                   notional * coupon_bp / 1e4 * (end - last.accrual_start).days / 360)
        return periods

    dates.payment_schedule = payment_schedule
    lib.pricing.payment_schedule = payment_schedule
    lib.payment_schedule = payment_schedule


def ignore_holidays(lib):
    lib.dates.holidays = lambda: frozenset()


def unrolled_dates(lib):
    """Coupon dates and the accrual start never moved to a business day (the cash settlement date still is)."""
    lib.dates.following_business_day = lambda day: day


def act_365(lib):
    lib.dates.DAY_COUNT_BASIS = 365
    lib.legs.DAY_COUNT_BASIS = 365


def no_accrual_on_default(lib):
    lib.legs.accrued_on_default = lambda *args, **kwargs: 0.0


def credit_triangle(lib):
    """Each hazard rate is the spread over one minus the recovery: the quote's for the flat curve, and the
    quotes' for the term structure (piece by piece), never fitted."""
    pricing = lib.pricing

    def fit_credit_curve(trade_date, quotes, recovery, discount):
        quotes = sorted(quotes)
        return lib.curves.CreditCurve(trade_date, [m for m, _ in quotes], [s / (1 - recovery) for _, s in quotes])

    pricing.fit_credit_curve = fit_credit_curve


def flat_hazard_for_the_curve(lib):
    """A contract priced off a name's curve with one flat hazard rate, fitted to the par spread interpolated
    (linearly in time) at the contract's maturity from the name's quotes."""
    pricing = lib.pricing

    def price_off_curve(trade_date, maturity, coupon_bp, notional, quotes, recovery, discount_curve):
        quotes = sorted(quotes)
        days = [(m - trade_date).days for m, _ in quotes]
        target = (maturity - trade_date).days
        i = min(max(bisect.bisect_left(days, target), 1), len(days) - 1)
        if target <= days[0]:
            spread = quotes[0][1]
        elif target >= days[-1]:
            spread = quotes[-1][1]
        else:
            (d0, s0), (d1, s1) = (days[i - 1], quotes[i - 1][1]), (days[i], quotes[i][1])
            spread = s0 + (s1 - s0) * (target - d0) / (d1 - d0)
        up = pricing.upfront_from_quoted_spread(trade_date, maturity, coupon_bp, spread, recovery, notional,
                                                discount_curve)
        return pricing.CurvePrice(par_spread=spread, quoted_spread=spread, upfront=up)

    pricing.price_off_curve = price_off_curve
    lib.price_off_curve = price_off_curve


def par_as_quoted(lib):
    pricing = lib.pricing
    original = pricing.price_off_curve

    def price_off_curve(*args):
        p = original(*args)
        return pricing.CurvePrice(par_spread=p.par_spread, quoted_spread=p.par_spread, upfront=p.upfront)

    lib.price_off_curve = price_off_curve


def paper_shortcuts(lib):
    """The paper's shortcuts: default only at monthly points (M=12) and premium accrued as half the coupon."""
    legs = lib.legs

    def protection_leg(dates, maturity_day, recovery, discount, credit):
        steps = max(1, round(maturity_day / 365 * 12))
        total, previous = 0.0, 0.0
        for k in range(1, steps + 1):
            day = maturity_day * k / steps
            total += (1 - recovery) * discount.discount_factor(dates.trade_date + dt.timedelta(days=round(day))) * (
                math.exp(credit.log_survival(previous)) - math.exp(credit.log_survival(day)))
            previous = day
        return total

    def accrued_on_default(period, coupon, step_in_day, discount, credit, trade):
        start = max((period.accrual_start - trade).days, step_in_day - 1)
        end = (period.accrual_end - trade).days - 1
        if end <= start:
            return 0.0
        amount = coupon * (period.accrual_end - period.accrual_start).days / 360
        default = math.exp(credit.log_survival(start)) - math.exp(credit.log_survival(end))
        return amount / 2 * default * discount.discount_factor(period.pay_date)

    lib.pricing.protection_leg = protection_leg
    legs.accrued_on_default = accrued_on_default


VARIANTS = {
    "reference": None,
    # open details
    "no_half_day": no_half_day, "no_series": no_series, "always_series": always_series,
    "benchmark_from_step_in": benchmark_from_step_in, "par_at_step_in": par_at_step_in,
    # details the conventions settle, read the other way
    "accrual_from_end_of_first_day": accrual_from_end_of_first_day, "survive_to_pay_date": survive_to_pay_date,
    "protection_from_end_of_step_in": protection_from_end_of_step_in, "value_at_trade_date": value_at_trade_date,
    "no_extra_day_at_maturity": no_extra_day_at_maturity,
    # lures
    "ignore_holidays": ignore_holidays, "unrolled_dates": unrolled_dates, "act_365": act_365,
    "no_accrual_on_default": no_accrual_on_default, "credit_triangle": credit_triangle,
    "flat_hazard_for_the_curve": flat_hazard_for_the_curve, "par_as_quoted": par_as_quoted,
    "paper_shortcuts": paper_shortcuts,
}


def run(variant) -> dict:
    lib = fresh()
    if variant:
        variant(lib)
    curve = lib.load_discount_curve(TMP / "data" / "discount-curve.csv")
    out = {}
    tie = []
    for r in TIE_OUTS:
        u = lib.upfront_from_quoted_spread(D(r["trade_date"]), D(r["maturity"]), float(r["coupon_bp"]),
                                           float(r["quoted_spread_bp"]), float(r["recovery"]), float(r["notional"]), curve)
        tie.append(f"{u.cash - float(r['cash']):+,.2f}")
    out["tie_outs"] = "cash off by $ " + " / ".join(tie)
    bad = sum(1 for c in CASES["schedules"]
              if [[p.accrual_start.isoformat(), p.accrual_end.isoformat(), p.pay_date.isoformat()] for p in
                  lib.payment_schedule(D(c["trade_date"]), D(c["maturity"]), c["coupon_bp"], c["notional"])]
              != [r[:3] for r in c["expected"]]
              or any(abs(p.amount - r[3]) > 0.01 for p, r in zip(
                  lib.payment_schedule(D(c["trade_date"]), D(c["maturity"]), c["coupon_bp"], c["notional"]),
                  c["expected"])))
    out["schedules"] = f"{bad} of {len(CASES['schedules'])} schedules differ"
    worst = {"bp": 0.0, "usd": 0.0, "tol": 0.0, "acc": 0.0}
    fails = 0
    for c in CASES["upfronts"]:
        u = lib.upfront_from_quoted_spread(D(c["trade_date"]), D(c["maturity"]), c["coupon_bp"], c["quoted_spread_bp"],
                                           c["recovery"], c["notional"], curve)
        err = abs(u.cash - c["expected"]["cash"])
        acc = abs(u.accrued - c["expected"]["accrued"])
        ratio = err / c["tolerance"]["cash"]
        worst = {"bp": max(worst["bp"], 0.5 * ratio), "usd": max(worst["usd"], err), "tol": max(worst["tol"], ratio),
                 "acc": max(worst["acc"], acc)}
        fails += ratio > 1 or acc > 0.01
    out["upfronts"] = (f"{fails} fail; largest {worst['bp']:.4f}bp-equivalent (${worst['usd']:,.2f}); "
                       f"accrued off by ${worst['acc']:,.2f}")
    worst_bp, fails, by_grade = 0.0, 0, {}
    for c in CASES["spreads"]:
        s = lib.quoted_spread_from_upfront(D(c["trade_date"]), D(c["maturity"]), c["coupon_bp"], c["points"],
                                           c["recovery"], curve)
        err = abs(s - c["expected"])
        worst_bp = max(worst_bp, err)
        by_grade[c["grade"]] = max(by_grade.get(c["grade"], 0.0), err)
        fails += err > 0.5
    out["spreads"] = (f"{fails} fail; largest {worst_bp:.4f}bp ("
                      + ", ".join(f"{g} {e:.3f}" for g, e in sorted(by_grade.items())) + ")")
    w = {"par": 0.0, "quoted": 0.0, "bp": 0.0, "usd": 0.0, "acc": 0.0}
    fails_price, fails_quoted = 0, 0
    for c in CASES["curve_contracts"]:
        p = lib.price_off_curve(D(c["trade_date"]), D(c["maturity"]), c["coupon_bp"], c["notional"],
                                [(D(m), s) for m, s in c["quotes"]], c["recovery"], curve)
        e = c["expected"]
        par, quoted = abs(p.par_spread - e["par_spread"]), abs(p.quoted_spread - e["quoted_spread"])
        err, acc = abs(p.upfront.cash - e["cash"]), abs(p.upfront.accrued - e["accrued"])
        ratio = err / c["tolerance"]["cash"]
        w = {"par": max(w["par"], par), "quoted": max(w["quoted"], quoted), "bp": max(w["bp"], 0.5 * ratio),
             "usd": max(w["usd"], err), "acc": max(w["acc"], acc)}
        fails_price += par > 0.5 or ratio > 1 or acc > 0.01
        fails_quoted += quoted > 0.5
    out["curve"] = (f"{fails_price} fail; par {w['par']:.4f}bp, upfront {w['bp']:.4f}bp-equivalent "
                    f"(${w['usd']:,.2f}), accrued ${w['acc']:,.2f}")
    out["curve_quoted"] = f"{fails_quoted} fail; largest {w['quoted']:.4f}bp"
    return out


if __name__ == "__main__":
    for name in sys.argv[1:] or list(VARIANTS):
        result = run(VARIANTS[name])
        print(f"== {name}")
        for check, text in result.items():
            print(f"   {check:13s} {text}")
