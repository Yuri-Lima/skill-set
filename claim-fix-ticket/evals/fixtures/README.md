# Test fixtures — Record-or-skip

Planted tickets and session state for `claim-fix-ticket` evals. Nothing
here is a real product.

Each case asks whether the agent **Records** a before video, **Skips**
only a finding with no screen, or **Stops** on unanswered auth.

Ground truth is in `../evals.json` under `expected_output`.
