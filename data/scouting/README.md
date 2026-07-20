# Qualitative scouting journal

`observations.jsonl` is an append-only journal of timestamped human observations. The file is intentionally absent until the first real observation is recorded; examples are not mixed with production evidence.

Each line follows `schema.json`. The original note is preserved alongside bounded structured signals from `-2` (strong negative) to `2` (strong positive). Confidence is between `0` and `1`.

When a note needs correcting, append a `retracted` record whose `retracts_observation_id` points to the old observation, then append the corrected observation. Do not rewrite what was believed before a deadline.

ChatGPT can turn natural-language match notes into these records. They can also be appended locally with:

```bash
python -m src.scouting_observations add \
  --player-id 123 \
  --player-name "Example Player" \
  --observed-at "2026-08-15T17:00:00+00:00" \
  --observer "David" \
  --note "Looked sharp and repeatedly moved into the box." \
  --confidence 0.8 \
  --attacking-role 2 \
  --movement-sharpness 2 \
  --expires-at "2026-09-01T23:59:00+00:00"
```

Observations decay with a 14-day half-life. The model caps their influence at plus or minus 12 expected minutes and an attacking-rate multiplier between `0.8` and `1.2`.
