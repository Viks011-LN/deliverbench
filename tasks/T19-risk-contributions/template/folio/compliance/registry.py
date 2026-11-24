"""The guideline registry: every guideline folio.compliance knows, and how a mandate becomes guidelines.

GUIDELINES is the one list of guideline classes. Its order is the order of
the mandate table and of the violations printed by ``check``. The mandate
reader learns from it which tables guidelines.toml may have and what kind of
value each takes, so a new guideline needs only:

1. a Guideline subclass in the family module it belongs to (concentration,
   composition, restricted) with a ``key``, a ``kind`` and measure();
2. an entry in GUIDELINES below;
3. a ``[guidelines.<key>]`` table in the client's guidelines.toml.
"""

from __future__ import annotations

from folio.compliance.composition import GovtMinShare, MaxPositions, MinCashShare
from folio.compliance.concentration import CountryMaxShare, FundMaxShare, IssuerMaxShare
from folio.compliance.guideline import Guideline
from folio.compliance.mandate import Mandate, load_mandate
from folio.compliance.restricted import RestrictedHoldings
from folio.compliance.restricted_list import RestrictedList

GUIDELINES: tuple[type[Guideline], ...] = (
    IssuerMaxShare,
    CountryMaxShare,
    FundMaxShare,
    GovtMinShare,
    MaxPositions,
    MinCashShare,
    RestrictedHoldings,
)

KINDS: dict[str, str] = {cls.key: cls.kind for cls in GUIDELINES}

MANDATE_FILE = "guidelines.toml"
RESTRICTED_FILE = "restricted.csv"


def guideline_class(key: str) -> type[Guideline]:
    for cls in GUIDELINES:
        if cls.key == key:
            return cls
    raise KeyError(f"unknown guideline {key!r}")


def read_mandate(path) -> Mandate:
    """Read a mandate file, accepting the guidelines in GUIDELINES."""
    return load_mandate(path, KINDS)


def needs_restricted_list(mandate: Mandate) -> bool:
    """Whether checking ``mandate`` means reading restricted.csv."""
    return mandate.in_force(RestrictedHoldings.key)


def build_guidelines(mandate: Mandate, restricted: RestrictedList | None = None) -> list[Guideline]:
    """The guidelines ``mandate`` has in force, in GUIDELINES order.

    ``restricted`` is required when needs_restricted_list(mandate) is true.
    """
    if needs_restricted_list(mandate) and restricted is None:
        raise ValueError(f"the mandate has {RestrictedHoldings.key} in force but no restricted list was given")
    return [guideline_class(term.key).from_term(term, restricted) for term in mandate.enabled_terms]
