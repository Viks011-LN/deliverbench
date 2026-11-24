"""The build-time reference for T11: ISDA's own CDS Standard Model library (C code v1.8.3), called through ctypes.

ISDA's code is never in this repository or in the room. It is built once, outside the repo's tracked files, from
the zip the owner downloaded after accepting its licence by hand (docs/job-plans/T11-PLAN.md):

    .cache/isda/isda_cds_model_c_v1.8.3.zip      sha256 ZIP_SHA256 below
    .cache/isda/src/isda_cds_model_c_v1.8.3/     unpacked; its license.txt is kept with it
    cd .cache/isda/src/isda_cds_model_c_v1.8.3/lib/build/dll/linux
    make C_CFLAGS="-g -c -fPIC -DUNIX -DLINUX -DVERSION=1.8.3 -Wno-error=implicit-function-declaration \
                   -Wno-error=int-conversion -Wno-error=incompatible-pointer-types -Wno-error=implicit-int"

(the makefile's own flags plus -fPIC for a shared library; the -Wno-error flags let a current gcc accept the
2009-era C; the one implicit declaration it warns about returns int, so nothing changes).

This file is our code: it only calls the library's published functions. The library does the pricing; what the
library leaves to its caller is set here by the standard contract's rules, each written in the desk's
conventions note (environment/app/docs/desk-conventions.md) and ticked in docs/job-plans/T11-TICKLIST.md:

  - the dates of a trade: step-in the calendar day after the trade date; cash settlement three business days
    after it; accrual from the latest quarterly coupon date (20 March, June, September, December) on or before the
    trade date, moved to the next business day if it is not one;
  - the calendar: Saturdays, Sundays and the desk's holidays (environment/app/data/holidays.csv) are not
    business days;
  - premium Actual/360, quarterly, coupon dates moved to the following business day, a short front stub ("f/s"),
    premium accrued paid on default, protection from the start of the step-in date;
  - the discount curve: the desk's zero rates, continuously compounded, Actual/365 Fixed, from the trade date;
  - the quoting convention (CDSone): one flat curve fitted to the contract itself with its coupon set to the
    quoted spread, starting on the contract's own accrual start;
  - the term structure: the name's par spreads at their maturity dates, all quoted as contracts traded today.
"""
from __future__ import annotations

import ctypes
import datetime as dt
import hashlib
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ZIP = REPO / ".cache" / "isda" / "isda_cds_model_c_v1.8.3.zip"
ZIP_SHA256 = "bee02772ef45c3ff93de995a1655b3c5231aec4e257173bc4d21d47c362e0db0"
SRC = REPO / ".cache" / "isda" / "src" / "isda_cds_model_c_v1.8.3"
LIBRARY = SRC / "lib" / "build" / "dll" / "linux" / "libcds.so"

TDate = ctypes.c_long
TBoolean = ctypes.c_int
SUCCESS = 0
CONTINUOUS = 5000.0
ACT_365F = 2
ACT_360 = 3
FOLLOW = ord("F")
CALENDAR = b"DESK"          # the desk's holidays, loaded from a file in ISDA's format; Saturdays and Sundays too


class TRatePt(ctypes.Structure):
    _fields_ = [("fDate", TDate), ("fRate", ctypes.c_double)]


class TCurve(ctypes.Structure):
    _fields_ = [("fNumItems", ctypes.c_int), ("fArray", ctypes.POINTER(TRatePt)), ("fBaseDate", TDate),
                ("fBasis", ctypes.c_double), ("fDayCountConv", ctypes.c_long)]


class TDateInterval(ctypes.Structure):
    _fields_ = [("prd", ctypes.c_int), ("prd_typ", ctypes.c_char), ("flag", ctypes.c_int)]


class TStubMethod(ctypes.Structure):
    _fields_ = [("stubAtEnd", TBoolean), ("longStub", TBoolean)]


class TFeeLeg(ctypes.Structure):
    _fields_ = [("nbDates", ctypes.c_int), ("accStartDates", ctypes.POINTER(TDate)),
                ("accEndDates", ctypes.POINTER(TDate)), ("payDates", ctypes.POINTER(TDate)),
                ("notional", ctypes.c_double), ("couponRate", ctypes.c_double), ("dcc", ctypes.c_long),
                ("accrualPayConv", ctypes.c_int), ("obsStartOfDay", TBoolean)]


class IsdaError(RuntimeError):
    pass


def zip_sha256() -> str:
    return hashlib.sha256(ZIP.read_bytes()).hexdigest()


class Isda:
    """ISDA's library, loaded once. Every price is per unit notional, as the library returns it."""

    def __init__(self, holidays: list[dt.date], library: Path = LIBRARY):
        if not ZIP.is_file() or zip_sha256() != ZIP_SHA256:
            raise IsdaError(f"ISDA's zip is not in the cache with sha256 {ZIP_SHA256} ({ZIP})")
        if not library.is_file():
            raise IsdaError(f"build ISDA's library first (see this file's docstring): {library}")
        lib = self.lib = ctypes.CDLL(str(library))
        lib.JpmcdsDate.restype = TDate
        lib.JpmcdsDate.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_long]
        lib.JpmcdsMakeTCurve.restype = ctypes.POINTER(TCurve)
        lib.JpmcdsMakeTCurve.argtypes = [TDate, ctypes.POINTER(TDate), ctypes.POINTER(ctypes.c_double), ctypes.c_int,
                                         ctypes.c_double, ctypes.c_long]
        lib.JpmcdsFreeTCurve.restype = None
        lib.JpmcdsFreeTCurve.argtypes = [ctypes.POINTER(TCurve)]
        lib.JpmcdsZeroPrice.restype = ctypes.c_double
        lib.JpmcdsZeroPrice.argtypes = [ctypes.POINTER(TCurve), TDate]
        lib.JpmcdsBusinessDay.restype = ctypes.c_int
        lib.JpmcdsBusinessDay.argtypes = [TDate, ctypes.c_long, ctypes.c_char_p, ctypes.POINTER(TDate)]
        lib.JpmcdsDateFromBusDaysOffset.restype = ctypes.c_int
        lib.JpmcdsDateFromBusDaysOffset.argtypes = [TDate, ctypes.c_long, ctypes.c_char_p, ctypes.POINTER(TDate)]
        lib.JpmcdsStringToStubMethod.restype = ctypes.c_int
        lib.JpmcdsStringToStubMethod.argtypes = [ctypes.c_char_p, ctypes.POINTER(TStubMethod)]
        common = [ctypes.c_double, TBoolean, ctypes.POINTER(TDateInterval), ctypes.POINTER(TStubMethod), ctypes.c_long,
                  ctypes.c_long, ctypes.c_char_p, ctypes.POINTER(TCurve)]
        for name in ("JpmcdsCdsoneUpfrontCharge", "JpmcdsCdsoneSpread"):
            fn = getattr(lib, name)
            fn.restype = ctypes.c_int
            fn.argtypes = [TDate] * 6 + common + [ctypes.c_double, ctypes.c_double, TBoolean,
                                                  ctypes.POINTER(ctypes.c_double)]
        lib.JpmcdsCleanSpreadCurve.restype = ctypes.POINTER(TCurve)
        lib.JpmcdsCleanSpreadCurve.argtypes = [TDate, ctypes.POINTER(TCurve), TDate, TDate, TDate, ctypes.c_long,
                                               ctypes.POINTER(TDate), ctypes.POINTER(ctypes.c_double),
                                               ctypes.POINTER(TBoolean), ctypes.c_double, TBoolean,
                                               ctypes.POINTER(TDateInterval), ctypes.c_long,
                                               ctypes.POINTER(TStubMethod), ctypes.c_long, ctypes.c_char_p]
        lib.JpmcdsCdsPrice.restype = ctypes.c_int
        lib.JpmcdsCdsPrice.argtypes = [TDate] * 5 + common + [ctypes.POINTER(TCurve), ctypes.c_double, TBoolean,
                                                              ctypes.POINTER(ctypes.c_double)]
        lib.JpmcdsCdsParSpreads.restype = ctypes.c_int
        lib.JpmcdsCdsParSpreads.argtypes = [TDate, TDate, TDate, ctypes.c_long, ctypes.POINTER(TDate), TBoolean,
                                            ctypes.POINTER(TDateInterval), ctypes.POINTER(TStubMethod), ctypes.c_long,
                                            ctypes.c_long, ctypes.c_char_p, ctypes.POINTER(TCurve),
                                            ctypes.POINTER(TCurve), ctypes.c_double, ctypes.POINTER(ctypes.c_double)]
        lib.JpmcdsCdsFeeLegMake.restype = ctypes.POINTER(TFeeLeg)
        lib.JpmcdsCdsFeeLegMake.argtypes = [TDate, TDate, TBoolean, ctypes.POINTER(TDateInterval),
                                            ctypes.POINTER(TStubMethod), ctypes.c_double, ctypes.c_double,
                                            ctypes.c_long, ctypes.c_long, ctypes.c_char_p, TBoolean]
        lib.JpmcdsFeeLegFree.restype = None
        lib.JpmcdsFeeLegFree.argtypes = [ctypes.POINTER(TFeeLeg)]
        lib.JpmcdsErrMsgEnableRecord.restype = ctypes.c_int
        lib.JpmcdsErrMsgEnableRecord.argtypes = [ctypes.c_int, ctypes.c_int]
        lib.JpmcdsErrGetMsgRecord.restype = ctypes.POINTER(ctypes.c_char_p)
        lib.JpmcdsErrMsgEnableRecord(20, 256)
        lib.JpmcdsHolidayLoadFromDisk.restype = ctypes.c_int
        lib.JpmcdsHolidayLoadFromDisk.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "desk.hol"
            path.write_text("".join(f"{d:%Y%m%d}\n" for d in sorted(holidays)), encoding="ascii")
            self._ok(lib.JpmcdsHolidayLoadFromDisk(CALENDAR, str(path).encode()), "holidays")
        self._epoch = dt.date(2000, 1, 1)
        self._epoch_t = lib.JpmcdsDate(2000, 1, 1)
        self.quarterly = TDateInterval(3, b"M", 0)
        self.stub = TStubMethod()
        self._ok(lib.JpmcdsStringToStubMethod(b"f/s", ctypes.byref(self.stub)), "stub")

    # ----- plumbing -----

    def _errors(self) -> str:
        lines = self.lib.JpmcdsErrGetMsgRecord()
        out = []
        i = 0
        while lines and lines[i] is not None:
            if lines[i]:
                out.append(lines[i].decode(errors="replace").strip())
            i += 1
        return " | ".join(out)

    def _ok(self, status: int, what: str) -> None:
        if status != SUCCESS:
            raise IsdaError(f"{what} failed: {self._errors()}")

    def tdate(self, day: dt.date) -> int:
        return self._epoch_t + (day - self._epoch).days

    def pydate(self, value: int) -> dt.date:
        return self._epoch + dt.timedelta(days=value - self._epoch_t)

    # ----- dates the library leaves to its caller (the standard contract's rules) -----

    def business_day(self, day: dt.date) -> dt.date:
        out = TDate()
        self._ok(self.lib.JpmcdsBusinessDay(self.tdate(day), FOLLOW, CALENDAR, ctypes.byref(out)), "business day")
        return self.pydate(out.value)

    def add_business_days(self, day: dt.date, n: int) -> dt.date:
        out = TDate()
        self._ok(self.lib.JpmcdsDateFromBusDaysOffset(self.tdate(day), n, CALENDAR, ctypes.byref(out)), "bus days")
        return self.pydate(out.value)

    def contract_dates(self, trade: dt.date) -> dict:
        """Step-in, cash settlement and accrual start of a standard contract traded on `trade`."""
        coupon = latest_coupon_date(trade)
        return {"trade": trade, "stepin": trade + dt.timedelta(days=1), "cash_settle": self.add_business_days(trade, 3),
                "accrual_start": self.business_day(coupon)}

    # ----- curves -----

    def discount_curve(self, base: dt.date, pillars: list[tuple[dt.date, float]]):
        dates = (TDate * len(pillars))(*[self.tdate(d) for d, _ in pillars])
        rates = (ctypes.c_double * len(pillars))(*[r for _, r in pillars])
        curve = self.lib.JpmcdsMakeTCurve(self.tdate(base), dates, rates, len(pillars), CONTINUOUS, ACT_365F)
        if not curve:
            raise IsdaError(f"discount curve: {self._errors()}")
        return curve

    def discount_factor(self, curve, day: dt.date) -> float:
        return self.lib.JpmcdsZeroPrice(curve, self.tdate(day))

    def free(self, curve) -> None:
        self.lib.JpmcdsFreeTCurve(curve)

    def credit_curve(self, trade: dt.date, quotes: list[tuple[dt.date, float]], recovery: float, discount):
        """The name's curve from par spreads (decimals) at maturity dates, every quote a contract traded today."""
        d = self.contract_dates(trade)
        ends = (TDate * len(quotes))(*[self.tdate(m) for m, _ in quotes])
        spreads = (ctypes.c_double * len(quotes))(*[s for _, s in quotes])
        curve = self.lib.JpmcdsCleanSpreadCurve(
            self.tdate(trade), discount, self.tdate(d["accrual_start"]), self.tdate(d["stepin"]),
            self.tdate(d["cash_settle"]), len(quotes), ends, spreads, None, recovery, 1, ctypes.byref(self.quarterly),
            ACT_360, ctypes.byref(self.stub), FOLLOW, CALENDAR)
        if not curve:
            raise IsdaError(f"credit curve: {self._errors()}")
        return curve

    def credit_curve_points(self, curve) -> list[tuple[dt.date, float]]:
        c = curve.contents
        return [(self.pydate(c.fArray[i].fDate), c.fArray[i].fRate) for i in range(c.fNumItems)]

    # ----- prices (per unit notional; positive when the protection buyer pays) -----

    def cdsone_upfront(self, trade: dt.date, maturity: dt.date, coupon: float, spread: float, recovery: float,
                       discount, clean: bool, benchmark_start: dt.date | None = None) -> float:
        d = self.contract_dates(trade)
        out = ctypes.c_double()
        self._ok(self.lib.JpmcdsCdsoneUpfrontCharge(
            self.tdate(trade), self.tdate(d["cash_settle"]), self.tdate(benchmark_start or d["accrual_start"]),
            self.tdate(d["stepin"]), self.tdate(d["accrual_start"]), self.tdate(maturity), coupon, 1,
            ctypes.byref(self.quarterly), ctypes.byref(self.stub), ACT_360, FOLLOW, CALENDAR, discount, spread,
            recovery, int(clean), ctypes.byref(out)), "upfront from quoted spread")
        return out.value

    def cdsone_spread(self, trade: dt.date, maturity: dt.date, coupon: float, upfront: float, recovery: float,
                      discount, clean: bool) -> float:
        d = self.contract_dates(trade)
        out = ctypes.c_double()
        self._ok(self.lib.JpmcdsCdsoneSpread(
            self.tdate(trade), self.tdate(d["cash_settle"]), self.tdate(d["accrual_start"]), self.tdate(d["stepin"]),
            self.tdate(d["accrual_start"]), self.tdate(maturity), coupon, 1, ctypes.byref(self.quarterly),
            ctypes.byref(self.stub), ACT_360, FOLLOW, CALENDAR, discount, upfront, recovery, int(clean),
            ctypes.byref(out)), "quoted spread from upfront")
        return out.value

    def price(self, trade: dt.date, maturity: dt.date, coupon: float, recovery: float, discount, credit,
              clean: bool) -> float:
        d = self.contract_dates(trade)
        out = ctypes.c_double()
        self._ok(self.lib.JpmcdsCdsPrice(
            self.tdate(trade), self.tdate(d["cash_settle"]), self.tdate(d["stepin"]), self.tdate(d["accrual_start"]),
            self.tdate(maturity), coupon, 1, ctypes.byref(self.quarterly), ctypes.byref(self.stub), ACT_360, FOLLOW,
            CALENDAR, discount, credit, recovery, int(clean), ctypes.byref(out)), "price")
        return out.value

    def par_spread(self, trade: dt.date, maturity: dt.date, recovery: float, discount, credit) -> float:
        d = self.contract_dates(trade)
        ends = (TDate * 1)(self.tdate(maturity))
        out = (ctypes.c_double * 1)()
        self._ok(self.lib.JpmcdsCdsParSpreads(
            self.tdate(trade), self.tdate(d["stepin"]), self.tdate(d["accrual_start"]), 1, ends, 1,
            ctypes.byref(self.quarterly), ctypes.byref(self.stub), ACT_360, FOLLOW, CALENDAR, discount, credit,
            recovery, out), "par spread")
        return out[0]

    def schedule(self, trade: dt.date, maturity: dt.date, coupon: float, notional: float) -> list[dict]:
        """Every coupon period of the contract: accrual start, accrual end (excluded), payment date, amount."""
        d = self.contract_dates(trade)
        leg = self.lib.JpmcdsCdsFeeLegMake(self.tdate(d["accrual_start"]), self.tdate(maturity), 1,
                                           ctypes.byref(self.quarterly), ctypes.byref(self.stub), notional, coupon,
                                           ACT_360, FOLLOW, CALENDAR, 1)
        if not leg:
            raise IsdaError(f"schedule: {self._errors()}")
        try:
            fl = leg.contents
            rows = []
            for i in range(fl.nbDates):
                start, end, pay = (self.pydate(fl.accStartDates[i]), self.pydate(fl.accEndDates[i]),
                                   self.pydate(fl.payDates[i]))
                rows.append({"accrual_start": start, "accrual_end": end, "pay_date": pay,
                             "amount": notional * coupon * (end - start).days / 360.0})
            return rows
        finally:
            self.lib.JpmcdsFeeLegFree(leg)


def latest_coupon_date(day: dt.date) -> dt.date:
    """The latest 20 March, June, September or December on or before `day` (not moved to a business day)."""
    year, month = day.year, day.month
    while True:
        if month in (3, 6, 9, 12) and dt.date(year, month, 20) <= day:
            return dt.date(year, month, 20)
        month -= 1
        if month == 0:
            year, month = year - 1, 12
