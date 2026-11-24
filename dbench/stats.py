"""The statistics of scoring 2.0 (docs/PLAN-V2.md section 4.5).

Run-level test, "on these jobs, does A deliver more often than B?": within each job, the runs of A and B are
shuffled between the two setups (every split of the job's delivered runs is equally likely under "no
difference"), and the statistic is the gap in delivery rate, each job weighted equally. The distribution is
computed exactly (a sum over jobs of independent hypergeometric counts), with fractions, so there is no
sampling error and no rounding. Two-sided: P(|gap| >= |observed gap|); the gap's expectation is zero.

Many pairs: Holm's step-down correction at 5% over every pair in the report.

One job: a call that leaving out a single job would remove is labelled "separated on one job (Txx)".

Range: the delivery rate's 95% range from a bootstrap over runs within each job (seeded, so it is the same on
every machine). It shows the noise of the runs on these jobs, not how the setup would do on other jobs.
"""
from __future__ import annotations

import random
from fractions import Fraction
from math import comb

ALPHA = Fraction(5, 100)
BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 0

Counts = dict[str, tuple[int, int]]  # job id -> (delivered runs, scored runs)


def _job_distribution(a_n: int, b_n: int, delivered: int) -> dict[Fraction, Fraction]:
    """The distribution of one job's rate gap a/a_n - b/b_n when its `delivered` runs are split at random between
    a_n runs of A and b_n runs of B."""
    total = comb(a_n + b_n, delivered)
    dist: dict[Fraction, Fraction] = {}
    for a in range(max(0, delivered - b_n), min(a_n, delivered) + 1):
        gap = Fraction(a, a_n) - Fraction(delivered - a, b_n)
        dist[gap] = dist.get(gap, Fraction(0)) + Fraction(comb(a_n, a) * comb(b_n, delivered - a), total)
    return dist


def run_level_p(a: Counts, b: Counts, jobs: list[str] | None = None) -> float:
    """Exact two-sided p-value of the run-level permutation test over the given jobs (default: every job both have).
    Jobs where neither setup's runs differ in outcome add nothing but are allowed."""
    common = sorted(jobs if jobs is not None else set(a) & set(b))
    if not common:
        raise ValueError("no job in common")
    dist: dict[Fraction, Fraction] = {Fraction(0): Fraction(1)}
    observed = Fraction(0)
    for job in common:
        (da, na), (db, nb) = a[job], b[job]
        if na == 0 or nb == 0:
            raise ValueError(f"{job}: a setup has no scored runs")
        observed += Fraction(da, na) - Fraction(db, nb)
        step = _job_distribution(na, nb, da + db)
        new: dict[Fraction, Fraction] = {}
        for x, px in dist.items():
            for y, py in step.items():
                new[x + y] = new.get(x + y, Fraction(0)) + px * py
        dist = new
    # Each job weighs the same: the gap in delivery rate is the sum over jobs divided by their number, which does
    # not change which outcomes are at least as extreme, so the sum is compared directly.
    p = sum((pr for value, pr in dist.items() if abs(value) >= abs(observed)), Fraction(0))
    return float(p)


def holm(p_values: dict, alpha: Fraction = ALPHA) -> dict:
    """Holm's step-down correction. Returns {pair: (threshold, separated)}: the pairs sorted by p-value face the
    thresholds alpha/m, alpha/(m-1), ...; the first pair that misses its threshold, and every pair after it, is not
    separated."""
    ordered = sorted(p_values.items(), key=lambda kv: (kv[1], str(kv[0])))
    m = len(ordered)
    out, still = {}, True
    for i, (pair, p) in enumerate(ordered):
        threshold = float(alpha) / (m - i)
        still = still and p <= threshold
        out[pair] = (threshold, still)
    return out


def carried_by_one_job(a: Counts, b: Counts, threshold: float) -> list[str]:
    """The jobs whose removal alone would undo a call made at this threshold."""
    common = sorted(set(a) & set(b))
    if len(common) < 2:
        return common
    return [job for job in common if run_level_p(a, b, [j for j in common if j != job]) > threshold]


def jobs_carrying(a: Counts, b: Counts) -> list[str]:
    """The jobs on which the setup ahead overall did better (the gap's source)."""
    common = sorted(set(a) & set(b))
    gap = sum(Fraction(a[j][0], a[j][1]) - Fraction(b[j][0], b[j][1]) for j in common)
    sign = 1 if gap >= 0 else -1
    return [j for j in common if sign * (Fraction(a[j][0], a[j][1]) - Fraction(b[j][0], b[j][1])) > 0]


def delivery_range(outcomes: dict[str, list[bool]], draws: int = BOOTSTRAP_DRAWS,
                   seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    """95% range of the delivery rate (each job weighted equally) by a bootstrap over runs within each job."""
    jobs = sorted(outcomes)
    if not jobs:
        raise ValueError("no runs")
    rng = random.Random(seed)
    rates = []
    for _ in range(draws):
        total = 0.0
        for job in jobs:
            runs = outcomes[job]
            total += sum(rng.choice(runs) for _ in runs) / len(runs)
        rates.append(total / len(jobs))
    rates.sort()
    return rates[int(0.025 * (draws - 1))], rates[int(0.975 * (draws - 1))]
