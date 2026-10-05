# Changelog

## 0.3.0 - 2026-10-05

- Many decisions at once: `Decider.ask` answers several questions about one situation in one call (choice, score from 1 to 10 levels, true/false); each question is pooled on its own, so adding a question never changes another answer. `Decider.predict_batch` and `ask_batch` run many requests through the network in one pass and return the same answers as one at a time. See docs/PARALLEL.md.
- `simthinkd bench --batch`: decisions per second one at a time and in batches, and the share of time spent encoding text, running the network and building answers. On our machine encoding is most of the time, so batching speeds up the network but not yet the whole call.
- Server: inference is serialised inside one process (a lock); a threaded server under heavy parallel load could crash in the BLAS library. Run several server processes for more throughput.
- Java runtime (`java/`): the same model in plain Java 8 inside your process, with `tools/export_java_weights.py`; `tests/test_java_parity.py` checks that it chooses exactly what Python chooses.
- README in Korean and Japanese, and a language switch on the project page.

## 0.2.1 - 2026-10-04

- Server: answers on a kept-alive connection took about 40 ms because headers and body go out as two small writes (Nagle's algorithm plus delayed ACK). `simthinkd serve` now sets TCP_NODELAY on every connection. Measured on Linux: median 42 ms before, 1.4 ms after, for clients that reuse connections (for example Java `HttpURLConnection`).
- `tests/test_server_latency.py` checks that a kept-alive request answers in under 20 ms.

## 0.2.0 - 2026-10-03

- Score models: `simthinkd.fit_score` and `Scorer` return one number (a risk level, a priority) instead of an action. Training is on the CPU; scoring needs only NumPy.
- `examples/risk_score.py`: a 0 to 100 risk score for parts on an inspection belt.
- README: "Where it fits", including two ways to use SimThink D with a large model (first filter, local backup), and where it is not a good fit.
- `tests/test_score.py` runs in CI.

## 0.1.0 - 2026-10-03

First public release.

- Python package with two Doom deciders (`doom-defend`, `doom-corridor`).
- `simthinkd` command line: `decide`, `serve`, `bench`, `train`, `list`.
- Train your own decider from a rule teacher with `simthinkd.fit`.
- Browser version in plain JavaScript, Gradio demo, Colab notebook.
- MCP server and LangChain tool.
