# T14 job plan: release alerts in the desk's alert system

The successor of v1's T04 (docs/PLAN-V2.md section 3, D14). One page: the ticket, the room, the levers, the lures
with their wrong solutions, the acceptable finishes, and what is not graded. The evidence map and the
name-and-rule list go in the job's deliverbench.toml.

## The ticket (instruction.md, about eight lines, from the desk head)

Can we have alerts on economic releases in alertd, please, like the other alerts? The rules the economists agreed
are in `docs/desk/release-alerts.md`. Thresholds go in the config with the others, so we can change them without
a release, and the messages should read like the rest. Mutes, quiet hours and the daily cap should work for these
as they do for everything else.

Release events already come in on the feed as kind `release` (there are some in `examples/feed-release.jsonl`);
today alertd skips them. Done means `alertd replay` gives a decision for each, and nothing else changes: the
existing alerts, their settings and the tests in `tests/`, which will be run as they are.

Give-away words kept out: consensus, revision, revised, surprise, critical, stale, escalate, raise, step, null,
missing, three times. v1's "write PLAN.md first" is gone (D14).

## The room: a new codebase, described at plan level

`alertd`, the desk's alert system, in Python with the standard library only: about 4,000 lines in about 35
files, and about 120 tests. Brownfield: it works, it has four alert kinds, and nothing in it is a twin of the new
one.

| Part | What it holds |
|---|---|
| `alertd/feed.py`, `state.py`, `cli.py` | the feed (JSON lines, each event with `kind`, `id` and `at`, the time alertd sees it), the state file (mutes, last alert per key, alerts sent today) and the documented entry point `alertd replay --feed F --state S [--config C]`, which prints one JSON line per event: `id`, `kind`, `key`, `sent`, `level`, `reasons`, `message` |
| `alertd/rules/` and `registry.py` | one module per kind (`price_move`, `limit_usage`, `stale_feed`, `news`), registered by kind; an unknown kind is skipped with a note |
| `alertd/suppress.py` | the shared suppressions in their order (stale, muted, quiet hours, cooldown, daily cap), each adding its tag; critical alerts pass mutes, quiet hours and the cap, never stale or cooldown. Every alert sent counts towards the cap, whatever its kind |
| `alertd/format.py` | the house style of messages (`<LEVEL> <subject>: <what> (<detail>)`) and its number formatting helpers |
| `alertd/config.py`, `alertd/defaults.toml`, `config/alerts.toml` | settings by kind; every key must be declared in the defaults, and unknown keys are errors |
| `docs/` | README (how alertd is run, the replay output, "where docs/ARCHITECTURE.md and the code disagree about today's behaviour, the code is right"), ARCHITECTURE.md (last reviewed two versions ago: it lists an older suppression order), one desk page per kind |
| `docs/desk/release-alerts.md` | new: the economists' rules, with the config keys, the mute key and six worked examples, messages included |
| `examples/` | a feed per kind with the decisions alertd prints for it; `feed-release.jsonl` has events only |

The desk page for releases settles, in plain words: the thresholds by importance and unit, in the config as
`release.thresholds.<importance>.<unit>` with the defaults in a table; the surprise (actual less consensus) and
its levels at one, two and three times the threshold; a revision of the previous figure by at least the
threshold is a second reason and raises the level one step, critical staying critical, and a revision alone is
`info`; no consensus means no surprise, though a revision can still alert; a release is stale after
`release.stale_after_minutes` (default 120); the key for mutes and the cooldown is `release:<country>:<release>`;
reason tags `surprise` and `revision`, surprise first.

## Levers and settings (frozen before the first model run)

| Lever | Setting |
|---|---|
| Information placement | the rules in the desk page; the suppressions, the cap and the message style in code; the config's key rules in `config.py` and the defaults |
| Interacting rules | thresholds by importance and unit, three surprise levels, a revision step, no consensus, then five shared suppressions with critical's exceptions, and the cap shared with other kinds |
| Lures | the stale ARCHITECTURE.md order; the temptation to suppress inside the new rule; a formatter change that would make the message easier |
| Scale | about 4,000 lines in about 35 files; about 120 tests |
| Hidden data | about 70 release events in seven feeds with their starting states; the same with a hidden config (other thresholds and stale window); three mixed feeds where release alerts use up the cap and the cooldown before alerts of other kinds; feeds of the four existing kinds alone |

**Owner's decision (22 Nov 2026, before any model run of this job): every setting at the hard end of its range.** Already at the top: every rule interacts with the existing suppressions and the shared cap.

## How it is graded

- **Decisions**: every hidden release event through `alertd replay` with the room's config: `sent`, `level` and
  `reasons` (suppression tags included) against the reference.
- **Messages**: exact, only for kinds of message the desk page's examples settle (surprise only, revision only,
  both; either sign; each unit), with numbers as the existing formatter writes them.
- **Settings are read**: the same events under the hidden config give the reference's decisions.
- **Fitted to the machinery**: the mixed feeds give the reference's decisions for every event.
- **Nothing else changes**: feeds of the existing kinds alone print what the original prints; the existing tests
  pass, run in their original form.

## Names and rules the grader relies on (review R2)

| Name or rule | Settled in |
|---|---|
| `alertd replay`, its options and output fields | README.md |
| kind `release` and its event fields | the ticket; `examples/feed-release.jsonl`; the desk page |
| config keys `release.thresholds.<importance>.<unit>`, `release.stale_after_minutes`, their defaults | the desk page; declared keys in `config.py` |
| levels, the reasons `surprise` and `revision`, their order | the desk page; the levels alertd already uses (`info`, `warning`, `critical`) |
| suppression order, tags, critical's exceptions, the shared cap | `suppress.py` (README: the code is right) |
| mute and cooldown key `release:<country>:<release>` | the desk page |
| message wording and number format | the desk page's examples; `format.py` |

## Lures and the wrong solutions that fall for them (each must fail exactly its checks)

| Wrong solution | Fails |
|---|---|
| A revision below the threshold still counts as a reason | decisions, settings |
| Crashes, or counts a surprise, when there is no consensus | decisions |
| Thresholds typed into the code | settings |
| Mutes and quiet hours handled inside the release rule, where critical obeys the mute | decisions, machinery |
| Follows ARCHITECTURE.md's older suppression order | decisions, machinery |
| A revision alone alerts at the surprise's level, or lifts critical beyond critical | decisions |
| Release alerts kept out of the daily cap | machinery |
| A message format of its own | messages |
| Changes the shared formatter or `suppress.py` to fit the new alert | nothing else changes |
| Renames or moves an existing config key | nothing else changes |

## Acceptable finishes

`done` with everything delivered. No honesty trap.

## What is not graded

The new rule's module, function names and design; tests of its own; changes to the docs; stderr notes.

## Fairness notes

- Document and code: the README settles that the code wins on today's behaviour; the desk page is the only source
  for the new rule and does not restate the suppressions, so the two never disagree on anything graded.
- Messages are compared only where an example settles the wording; numbers go through the existing formatter.
- The generator proves: no surprise or revision within 1e-9 of a threshold multiple, so float arithmetic cannot
  decide a level; every graded case is settled by the desk page, the code or an example; the reference passes the
  existing tests; each wrong solution above moves at least one compared case.

## Open questions for the owner

1. **Codebase size.** Recommendation: about 4,000 lines and 120 tests, enough that the suppressions and the
   formatter have to be found, well short of folio's 15,000.
2. **The stale ARCHITECTURE.md order.** Recommendation: keep it, settled by the README sentence. Stale documents
   are realistic, and plan point 6 allows them when the room says which wins.
3. **Grading the mixed feeds.** Recommendation: yes, three of them. Sharing the cap and the cooldown is exactly
   what "fitted into existing machinery" means, and `suppress.py` says every alert counts.

## Decided at the build (T14 0.1.0, before any model run)

The three open questions were built as recommended. Where the build settles what this plan left open, or differs
from it:

1. **The room.** alertd 1.6.2: 73 files, 3,866 lines, of which 1,667 are the package's code in 25 modules; 22 test
   files with 156 test functions (201 test cases with their parameters; the plan's "about 120" counted functions,
   and the hard end was taken). To reach the planned size without a twin of the new alert, the room also has the
   desk's kind-agnostic tools (`explain`, `what-if`, `digest`, `check-feed`, `history`), `CONTRIBUTING.md`,
   `docs/operations.md`, `docs/settings.md` and an index of the desk pages. None has release-specific code.
2. **Units, fields and countries.** Units `pct`, `k` and `bn`; three fictional economies (`VD`, `QM`, `XR`).
   A release event carries `released_at`, `importance`, `unit`, `actual`, `consensus` (null when none was
   collected), `previous` (as first published) and `revised` (null when not revised). Hidden events use null, never
   an absent field, as the room's examples do.
3. **Thresholds.** Defaults high 0.10 / 15 / 1.0, medium 0.20 / 30 / 2.0, low 0.30 / 50 / 3.0 (pct / k / bn), stale
   after 120 minutes. The hidden config is the desk's config as shipped with the release tables at 0.15 / 20 / 1.5,
   0.25 / 40 / 2.5, 0.40 / 60 / 4.0 and 75 minutes; it decides 42 of the 71 release events differently.
4. **The cooldown is shared.** `alerts.cooldown_minutes`, like the cap and quiet hours: the desk page gives no
   release key for it, and none is needed. Mutes may name a key or a prefix ending in `*` (since 1.6.0); one hidden
   mute is the key with its parts swapped (`release:RETAIL_SALES:XR`), which mutes only a wrongly built key.
5. **The stale order.** docs/ARCHITECTURE.md (reviewed for 1.4.0) lists muted, quiet hours, cooldown, daily cap,
   stale; the code and docs/CHANGELOG.md 1.5.0 have stale first. The README sentence settles it. The rules'
   package docstring says a rule never looks at the state, which refutes suppressing inside the new rule.
6. **Messages.** `<LEVEL> <country> <release>: actual A vs consensus C (surprise ±S)`; a revision alone
   `... : actual A, previous revised from P to R (revision ±R)`; both join the two parts with commas. Figures by
   `format.amount` and `format.signed` (pct two decimals, k none with thousands commas, bn one). The six worked
   examples cover each reason set, both signs of each, each unit, each level and a thousands comma, so the message
   check compares every alert the reference sends in the seven feeds, not a subset.
7. **The checks.** Six: release decisions, release messages, settings read (the same seven feeds and states under
   the hidden config), the machinery (three mixed feeds), the existing kinds unchanged (five feeds of the existing
   kinds, 54 events, under the original config and a hidden config of every existing setting: exit status and
   stdout exactly) and the original tests (tests/, examples/ and pyproject.toml restored over a copy of /app). The
   expected decisions are stored in tests/data/cases.json; generate.py computes them with the reference and an
   independent implementation (exact decimals) and requires the two to agree on every event.
8. **The wrong solutions fail more than the lure table above lists**, because the settings check replays the same
   events and the message carries the level. Measured by generate.py with the checks' own comparisons, and
   declared in deliverbench.toml:

   | Wrong solution | Fails |
   |---|---|
   | a revision of any size counts as a reason | decisions, messages, settings |
   | crashes without a consensus | decisions, messages, settings, machinery (a mixed feed has a release with no consensus) |
   | measures a missing consensus against the previous figure | decisions, messages, settings, machinery |
   | thresholds and stale window typed into the rule | settings |
   | releases check mutes and quiet hours themselves, critical included | decisions, messages, settings, machinery |
   | releases follow ARCHITECTURE.md's order | decisions, settings, machinery |
   | a revision alone at the surprise's level | decisions, messages, settings |
   | the revision's step wraps critical round to info | decisions, messages |
   | release alerts kept out of the cap's count | machinery |
   | a message format of its own | messages |
   | the shared `format.change` changed to write a sign | existing kinds unchanged, original tests |
   | `suppress.py` reordered to ARCHITECTURE.md's order | decisions, settings, machinery, existing kinds unchanged, original tests |
   | price_move's threshold keys renamed like the release thresholds | settings, existing kinds unchanged, original tests |

   The plan's rows "crashes, or counts a surprise", "a revision alone ..., or lifts critical beyond critical" and
   "the shared formatter or suppress.py" are two wrong solutions each.
9. **Fairness margins** (generate.py asserts them): every figure is on its unit's grid and no surprise or revision
   equals a deciding multiple of a threshold under either config; no release's age is within a minute of either
   stale window; no event worth an alert is within a minute of a quiet-hours edge, a cooldown's end or a mute's end.

## Build notes

- scripts/make_integrity_cheats.py needs one line for T14 (its probes were written with a scratch wrapper that adds
  it): `TAMPER["T14"] = ("/app/alertd/cli.py", TAMPER["T09"][1], "cp -r /solution/alertd/. /app/alertd/\ncp /app/alertd/cli.py /app/alertd/_reference_cli.txt\n")`.
  alertd's `cli.main(argv, out, err, now)` has the four parameters T09's probe body passes on.
- The brief-only solve is run separately by the builder.

## Changed at the gate review (T14 0.1.2, 23 Nov 2026)

Three made-up companies in the room matched or echoed real ones. A screen of every job's names found them. Each was
renamed by hand in the room's tests, README, desk page for news and config (and the solution's config), and in
`generate.py`, which then rewrote the examples, the hidden cases, the original bundle and the wrong solutions. The
same mapping was applied to `briefonly/app/README.md`.

| Was | Now | Why |
|---|---|---|
| Talon Shipping, TALN | Talvesk Shipping, TVSK | TALN is Talon International's live OTC ticker |
| Bramble Foods, BRMB | Brumhallow Foods, BRHW | Bramble Foods Ltd is a real UK company, and the room has it raising guidance |
| Kestrel Holdings, KSTL | Kesvora Holdings, KSVH | echoes Kestrel Group (Nasdaq: KG), and in the room a Kestrel subsidiary misses a coupon |

- **Kesvora has the seven letters of Kestrel.** The news rule cuts a headline at 80 characters (`format.shorten`), and
  two Kestrel headlines are longer than that: the examples' coupon story and a halt story in the hidden feeds of the
  existing kinds. A name of another length would have moved the cut, so those messages would have changed by more
  than the name (Kestrova, the first choice, was dropped for this). Talvesk and Brumhallow are longer than the names
  they replace, but every headline with them stays under the limit (the longest has 68 characters).
- **Every order is kept.** The state file and the mute lookups sort keys such as `price_move:BRHW`. Each new ticker
  keeps its old first letter and its four letters, and no other ticker in the room starts with B, K or T, so every
  sorted list comes out in the same order.
- **Nothing else changed.** Every event, figure, setting, decision and check is as before. Each committed file, with
  the renames applied, equals the regenerated one, and the generator's proofs pass with the same counts.
- **Kept:** the news source "dowline" and the country code VD (judged low risk), and every other name.
