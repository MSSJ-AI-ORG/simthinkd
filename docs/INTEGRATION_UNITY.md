# Integrating SimThink D with a Unity simulator

## 1. Process layout

- The decider runs as a separate local process (`simthinkd serve <decider>`) on the same machine as the simulator.
- The simulator is the HTTP **client**. One decision request in flight at a time per agent.
- For remote-decider arms, point the same client at a relay URL or at `mock_decider.py --delay-ms 250 --jitter-ms 30`.

## 2. Asynchronous loop (C#, simplified)

```csharp
// Fixed simulation step (e.g. 35 Hz) driven by an accumulator; rendering is independent.
class DecisionAgent {
    Task<Reply> pending; int sentTick; string lastAction = "ADVANCE";
    public void OnSimTick(int tick, SimState s) {
        if (pending != null && pending.IsCompleted) {
            var r = pending.Result;                       // apply at this tick
            lastAction = Valid(r) ? r.Choice : Fallback(); // unknown choice -> first action, logged invalid
            Log.Decision(sentTick, tick, r.RoundTripMs, lastAction);
            pending = null;
        }
        if (pending == null) {                            // request a new decision
            sentTick = tick;
            pending = client.PostAsync(BuildRequest(Perception.Sentence(s)));
        } else {
            Log.SkippedTick(tick);                        // decision still pending: this tick is skipped
        }
        Vehicle.Apply(lastAction);                        // the last action repeats while waiting
    }
}
```

- Use `HttpClient` with a keep-alive connection and a 10 s timeout; measure round trip with `Stopwatch`.
- Never block the simulation thread on the request. In synchronous (control) mode, pause the fixed step until the reply arrives.
- Health check before a run: `GET /health`, compare `weights_sha256` with the expected hash from the run config; abort on mismatch.

## 3. Arms to support

| Arm | Decides | Waits for |
|---|---|---|
| T0 | rule teacher (in C#) | nothing |
| S | rule teacher | a real call to the decider (answer discarded) |
| D | SimThink D | its own call |
| J | remote decider (URL) | its own call |
| SJ | rule teacher | a replayed latency drawn from a file of measured latencies |
| INJ(k) | any | fixed extra delay k ms after each call |
| HOLD(k) | decider | holds the freshly applied action for k ticks before reading the next state |

## 4. Logs

Per job (JSON, written atomically at the end): arm, scenario, seeds, tick rate, mode, url, expected hash, git commit, host,
per-episode `{seed, ticks, decisions, engine_ticks_skipped, decision_ms_p50, decision_ms_p90, invalid, outcome metrics,
teacher_agreement}` and optional gzip per-tick traces. These feed our analysis scripts unchanged.

## 5. Training data from the simulator

Run the rule teacher in synchronous mode on training seeds and write one row per decision in the format of
`simthinkd.toy` and `simthinkd.fit` (`request` = exactly what the client would send; `expected` = the teacher's choice).
Hand us the three `.jsonl.gz` files or train locally with `simthinkd.train`.
