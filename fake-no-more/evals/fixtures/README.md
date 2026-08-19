# Test fixtures — deliberately wrong on purpose

These files contain **planted factual errors**. They are inputs for testing the
skill, not examples of good work, and nothing in them is real: the service, the
contracting parties, and the support data are all invented.

Each fixture pairs a **claim artifact** with the **primary source** that
contradicts it:

| Fixture | Claim artifact | Primary source |
|---|---|---|
| `repo-audit/` | `README.md` | the code tree itself |
| `contract-review/` | `memo-interno.md` | `servicos-agreement.md` |
| `data-report/` | `qbr-summary.md` | `tickets-2026-q2.csv` |

Every fixture deliberately contains three kinds of claim, because an auditor that
only hunts for errors fails just as badly as one that finds none:

- claims that are **wrong** and should be caught
- claims that are **correct** and should be confirmed, not nitpicked
- claims that are **unverifiable** from the material provided and should be
  marked as such rather than guessed at

Ground truth for each is in `../evals.json` under `expected_output`.
