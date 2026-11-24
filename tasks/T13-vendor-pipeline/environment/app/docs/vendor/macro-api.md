# Woodgrove Macro Data: API reference

Version 3.2, June 2026. For subscribers on a desk line.

Woodgrove Macro Data publishes monthly macroeconomic series, with every revision kept. This document describes the
HTTP API that serves them: its endpoints, what each answer holds, and its terms of use. Everything it describes
happens in normal operation.

## Contents

1. Basics
2. Endpoints
3. Values
4. Vintages
5. Series ids and retired series
6. The gateway
7. Rate limits
8. Status codes
9. Release calendar
10. Document history

## 1. Basics

- A line is a subscriber's connection to the API. Its base address is given with the line; the paths below are
  relative to it.
- Every endpoint answers `GET` with JSON in UTF-8. A desk line needs no key.
- Months are written `YYYY-MM` and dates `YYYY-MM-DD`.
- Every series is monthly and has an id in capitals, such as `IP_YOY`. Ids come with the subscription; the API has
  no search.
- An answer normally arrives within a second.

## 2. Endpoints

### 2.1 Observations: `GET /series/<id>?page=<n>`

One page of a series' observations. Pages are numbered from 1, and `page` defaults to 1. A page holds up to 24
observations, in order of `date`, then of `vintage`. `next_page` is the number of the following page, or `null` on
the last page.

The id and the figures in this example are illustrative:

    GET /series/RETAIL_YOY?page=1

    200
    {
      "id": "RETAIL_YOY",
      "page": 1,
      "observations": [
        {"date": "2024-01", "value": "2.84", "vintage": "2024-02-14"},
        {"date": "2024-02", "value": "3.02", "vintage": "2024-03-14"},
        ...
      ],
      "next_page": 2
    }

| Field | Meaning |
|---|---|
| `id` | the series |
| `page` | the number of the page this answer holds |
| `observations` | up to 24 observations, in order of `date`, then of `vintage` |
| `observations[].date` | the month the figure is for |
| `observations[].value` | the figure, as a decimal string (section 3) |
| `observations[].vintage` | the date this figure was published (section 4) |
| `next_page` | the number of the following page, or `null` on the last page |

### 2.2 Series information: `GET /series/<id>/meta`

    {
      "id": "RETAIL_YOY",
      "title": "Retail sales, year on year",
      "units": "percent, year on year",
      "frequency": "monthly",
      "first": "2024-01",
      "last": "2026-06",
      "months": 30,
      "last_updated": "2026-07-14"
    }

`first` and `last` are the first and last months the series covers, and `months` is the number of months from one
to the other, each counted once however many vintages it has. `last_updated` is the date of the series' latest
vintage.

### 2.3 Status: `GET /health`

Answers `{"ok": true}` while the service is up. It is not counted against the rate limit (section 7).

## 3. Values

Figures are percentages, published to two decimal places. `value` carries a figure as a decimal string, such as
`"2.31"` or `"-0.47"`.

"." means no figure was published for that month; it is not zero. Every month from `first` to `last` appears in
the series, with "." where no figure was published.

## 4. Vintages

Figures are revised after they are first published, and every vintage is kept. Each observation carries `vintage`,
the date on which its figure was published.

A month revised since first publication appears once per vintage, oldest first. The figure as it stands today is
its latest vintage. A month that has never been revised appears once.

A page holds 24 observations, whatever months they belong to, so a month's vintages may continue on the next page.

## 5. Series ids and retired series

An id that was never issued answers 404. A retired id is never issued again.

A retired series answers 410 with `replaced_by` naming its successor, which replaces it from then on:

    {"error": "series retired", "replaced_by": "<successor id>"}

The successor carries the retired series' whole history, revisions included, in the same pages. Series are retired
without notice, and a successor may itself be retired later, so a client keeps the id it was given and follows
`replaced_by` whenever it meets a 410; it does not write a successor's id into its own code or settings.

## 6. The gateway

Every request passes through a shared gateway, and the gateway answers some requests itself:

- 429, when the line's allowance is used up (section 7).
- 500, 502 and 503 are passing errors: they come from the gateway's load, not from the request, and the same
  request is answered normally when it is sent again.
- Under load the gateway may answer a request for a page with the page before it. A response's `page` always names
  the page it holds, and the page asked for is served when it is asked for again.

Rate limits (429), passing errors (500, 502, 503) and repeated pages can come at any request, whatever the
client's pattern of requests: how many it makes, in what order and how fast.

## 7. Rate limits

One request at a time: a line may not send a request while another of its requests is unanswered.

Each line has an allowance of requests, renewed continuously. When the allowance is used up the answer is 429 with
`Retry-After` in seconds, and no request may be sent until it has passed. The wait counts from the moment the 429
arrives. `Retry-After` is always a whole number of seconds, and a request answered 429 is not served.

Requests sent before a wait is over, and requests sent while another is unanswered, are recorded against the line;
repeated breaches suspend it.

## 8. Status codes

Every error answer has a JSON body whose `error` field says in words what went wrong.

| Status | Meaning |
|---|---|
| 200 | the answer asked for |
| 400 | a malformed request, for example a `page` that is not a whole number |
| 404 | no such page or endpoint, or an id that was never issued |
| 410 | a retired series (section 5) |
| 429 | the line's allowance is used up (section 7) |
| 500, 502, 503 | a passing error (section 6) |

## 9. Release calendar

New figures and revisions are published on release days, around the middle of the month after the month they are
for. A release may revise any earlier month; once a year, in March, a benchmark revision may revise months several
years back. Between release days the figures do not change.

## 10. Document history

| Version | Date | Change |
|---|---|---|
| 3.2 | June 2026 | The series information endpoint, `/series/<id>/meta` |
| 3.1 | November 2025 | Page size counted in observations, vintages included |
| 3.0 | March 2024 | Vintages on every observation; values as decimal strings |
