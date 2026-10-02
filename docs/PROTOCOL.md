# SimThink D decision protocol (v1)

One decision per HTTP request. The caller (simulator, game, robot controller) describes the current situation and the
offered actions; the decider returns one choice with a probability for every offered action.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{"model", "weights_sha256", "delay_ms"}` — the caller must compare `weights_sha256` with the expected hash before a run |
| POST | `/v1/systemone` | a decision (below) |

## Request

```json
{
 "model": "<free text, e.g. iron-tempo-v1>",
 "state": {
  "page": {"url": "sim://<domain>/<scenario>", "title": "<short context, e.g. 'tick 1234'>", "text": "<STATE SENTENCE>"},
  "elements": [{"id": "<ACTION>", "role": "button", "label": "<ACTION>"}],
  "recent_actions": [{"action": "<ACTION>", "page_changed": true}]
 },
 "questions": {
  "operation": {"type": "choice",
                "criteria": {"<ACTION>": "<one-line description>" , "...": "..."},
                "instructions": {"goal": "<one-line goal>", "rules": "<optional operator rule text>"}},
  "<action>_target": {"type": "choice", "criteria": {"<TARGET>": "<description>"}}
 }
}
```

- `criteria` values may be a string or `{"element": "[button] X", "description": "..."}`.
- **At most 8 operations** (top-level actions) per request in this release. Use a second level `<operation lowercased>_target`
  for variants (for example `REJECT` with targets `BIN_SCRATCH`, `BIN_DENT`). Up to 1,500 rows in total.
- **State sentence:** a short, binned, human-readable description produced by a deterministic perception script from the
  exact simulation state (for example `threats: FPVdrone front-left near closing | self: hull 72% | smoke ready`).
  Never pass raw coordinates or floats with many digits; bin them into words. Keep the vocabulary stable across runs.
- `recent_actions` is optional (most recent last).

## Reply

```json
{
 "model": "simthink-d:<weights stem>",
 "answers": {
  "operation": {"choice": "<ACTION>", "probabilities": {"<ACTION>": 0.93, "...": 0.01}, "confidence": 0.93},
  "<action>_target": {"choice": "<TARGET>", "probabilities": {...}, "confidence": 0.88}
 },
 "usage": {"external_model_calls": 0},
 "meta": {"total_ms": 1.9, "infer_ms": 1.9, "delay_ms": 0, "weights_sha256": "...", "answered_at": "<UTC ISO time>"}
}
```

- The `_target` answer appears only when the chosen operation has a target question.
- `confidence` = probability of the chosen option. Callers may hand low-confidence decisions to a slower judge.
- Errors: HTTP 400 for a malformed request (caller should apply its fallback action and log it as invalid).

## Timing rules for real-time use (why this matters)

The caller must **not pause the simulation** while waiting (asynchronous mode): count every tick that passes without a new
decision as a *skipped tick* and keep repeating the last action. Log per decision: tick sent, tick applied, round-trip ms.
The same contract is used for the local decider (about 2 ms), a mock with added delay, and remote deciders (about 250 ms),
so arms differ only in who answers and how long it takes.
