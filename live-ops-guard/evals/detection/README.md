# Detection evals

`cases.jsonl` is the labelled corpus the secret and secret-store-read detectors are
scored against. `scripts/eval-detection.py` runs it (also from `scripts/test-guard.sh`)
and reports precision / recall per kind.

One line per case:

```json
{"id": "tp-env-password", "tier": "must", "kind": "secret", "text": "DB_PASSWORD=…", "expect": ["assignment-secret"], "note": "…"}
```

- `tier`: `must` gates the suite (exit 1 on any failure); `stretch` is reported only —
  a known limit we accept, with the reason in `note`.
- `kind`: `secret` → `find_secrets(text)`; `read` → `secret_read_findings(command)`;
  `shell` → the finding kinds of a whole `run_terminal_command` classification.
- `expect`: the exact set of kinds. `[]` means "must stay silent" — false alarms are
  scored as failures, same as misses.

Rules: every value is synthetic, and the file never holds a matchable token **at rest**:
write `ghp_{{A*36}}`, not the expanded string, and split provider prefixes and documented
example values into `{{lit:…}}{{lit:…}}` halves (`{{lit:AK}}{{lit:IA}}…`). The runner
expands templates before scoring. That keeps GitHub push protection, secret scanners and
`grep` quiet about a file whose whole purpose is to look like leaks. Never a real credential. When a real session shows a miss or a false alarm, add the case first,
watch it fail, then fix the detector: the corpus is the memory of what bit us.

Run:

```bash
python3 scripts/eval-detection.py            # full report with the per-kind table
python3 scripts/eval-detection.py --quiet    # failures and totals only
python3 scripts/eval-detection.py --only fp- # a subset by id prefix
```
