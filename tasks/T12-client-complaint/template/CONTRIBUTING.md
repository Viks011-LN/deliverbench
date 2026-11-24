# Contributing to folio

folio prints what clients receive. A client's statement is `folio value` and
the trade ledger they are sent is `python -m folio.ledger export`, each run on
the client's own data folder. Support keeps what was sent, with the data
folder it came from, in `support/<case>/`, so a figure a client questions can
be printed again here.

## Fixing a bug

- A fix goes in the `folio` package. It changes what was wrong and nothing
  else that folio prints.
- Release checks run the package on other data folders than the ones in this
  repo, so a change that only makes one folder's report come out right is not
  a fix. A client's files are never edited to make a report agree: they are a
  record of what was sent.
- Every fix comes with a regression test, in a new file in `tests/` named
  `test_<what>.py`. At least one of its tests fails on the code before the fix,
  by an assertion, and all of them pass after it. So the test uses only
  functions and commands that exist before the fix: a test that fails because
  it imports something new proves nothing.
- Release checks run that file against the package before the fix and after
  it, each time in a copy of this folder with the existing tests. Import
  `folio` as the existing tests do, and find any file the test reads relative
  to the test file itself.
- Existing tests are never edited.
- The whole suite passes (`python -m pytest`) before a fix is handed in.
