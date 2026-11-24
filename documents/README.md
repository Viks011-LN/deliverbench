# Third-party documents

T11 (price standard CDS) puts two published documents in the room, as a desk colleague would have them open. They
are shipped here unchanged, so the room can be built without depending on outside addresses.

| File | Document | Where it comes from |
|---|---|---|
| `okane-turnbull-2003.pdf` | Dominic O'Kane and Stuart Turnbull, *Valuation of Credit Default Swaps*, Lehman Brothers, Fixed Income Quantitative Credit Research, April 2003 (19 pages) | A copy that circulates publicly; the paper has no publisher's address today |
| `isda-numerical-fix-2012.pdf` | *ISDA CDS Standard Model: Proposed Numerical Fix*, Markit, November 2012 | ISDA's CDS model site (the address is in T11's `deliverbench.toml`) |

These files are not covered by this repository's licence: their rights stay with their owners. They are included
unchanged and only so that T11 can be run.

`dbench documents tasks/T11-cds-pricing` reads them from here, checks each against the checksum recorded in T11's
`deliverbench.toml`, converts it to text and writes the room files. The ISDA note can also be downloaded from its
address if this copy is missing.
