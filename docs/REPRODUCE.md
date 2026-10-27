# What you can reproduce from the paper

The paper: Shin, Lee, Jeong and Kwon, "Separating Decision Time from Decision Quality in the Real-Time Gap of Distilled Deciders: Evidence from a Game and a Conveyor Simulator". Preprint: [arXiv:2610.04810](https://arxiv.org/abs/2610.04810).

Software version: the paper links the software release v0.1.0 (git tag `v0.1.0`, software DOI [10.5281/zenodo.23111615](https://doi.org/10.5281/zenodo.23111615)). The weight files and the decision code (`policy.py`) are unchanged since v0.1.0, so `predict()` gives the same answers in later versions. Later versions add features (for example parallel questions and batches, see [PARALLEL.md](PARALLEL.md)). To rerun with the exact release: `pip install simthinkd==0.1.0`.

## The deciders are the paper's deciders

The two weight files in this package are the original deciders evaluated in the paper (called O there). You can check the hashes yourself.

| Preset | File | SHA-256 (first 10) | In the paper |
|---|---|---|---|
| `doom-defend` | `src/simthinkd/weights/doom-defend.npz` | `a814587e03` | original decider O, defend_the_center |
| `doom-corridor` | `src/simthinkd/weights/doom-corridor.npz` | `a164d90514` | original decider O, second scene (deadly_corridor) |

```bash
python -c "import hashlib, simthinkd, pathlib; p = pathlib.Path(simthinkd.__file__).parent / 'weights'; [print(f.name, hashlib.sha256(f.read_bytes()).hexdigest()[:10]) for f in sorted(p.glob('*.npz'))]"
```

## What this repository reproduces

| Paper item | How to run it here |
|---|---|
| The decider: 265,665 parameters, hashed word and letter features, scores every offered action | `from simthinkd import Decider` (see the README) |
| Decision time on recorded Doom states | `simthinkd bench` (1,050 recorded states, one request at a time) |
| The decision request and reply format used in all studies | [docs/PROTOCOL.md](PROTOCOL.md), `simthinkd serve` |
| The conveyor-inspection simulator with a 400 ms deadline (the paper's second environment) | [examples/factory_twin](../examples/factory_twin/) |
| Figures for the main contrasts and the conveyor deadline | [docs/FIGURES.md](FIGURES.md) |

Your timing numbers will differ from the paper's. They depend on your CPU and operating system, and the paper shows that the host matters.

## Screen benchmark (0.5.0)

The screen numbers in the README and [SCREEN.md](SCREEN.md) come from `benchmarks/screen`: two synthetic apps (an HR ERP
and an image studio), local headless Chrome, and a large model plugged in through one command.

```bash
python -m pip install -e ".[train]" pillow websocket-client pytest
cd benchmarks/screen
python -m pytest -q test_bench_offline.py                                    # offline, no Chrome
python run.py --app erp --cond decider --seed 502 --reps 3 --out runs/erp_decider
python run.py --app erp --cond llm     --seed 502 --reps 3 --out runs/erp_llm --llm-cmd '["python", "bridge_codex.py"]'
python run.py --app img --cond decider --seed 601 --reps 3 --out runs/img_decider --llm-cmd '["python", "bridge_codex.py"]'
python run.py --app img --cond llm     --seed 601 --reps 3 --out runs/img_llm --llm-cmd '["python", "bridge_codex.py"]'
```

Each run writes `SUMMARY.json` and one timing file per repetition. Seeds, conditions and order are the ones we sealed
before measuring. Times depend on your machine and on the large model's response time; success counts and large-model
calls are the parts to compare. Missions, plans and app files are the same on every run, but teacher screenshots are
rendered fresh each time, so the trained screen decider can differ by bytes between two runs. The live shopping-site figures in SCREEN.md are not reproducible from this repository:
that code is not published.

## What is not in this repository yet

| Paper item | Status |
|---|---|
| The ViZDoom study harness (scripted teacher, latency-matched control, asynchronous play) | Not released yet |
| Preregistrations with their SHA-256 hashes | Available to reviewers on request |
| Analysis scripts and per-episode logs | Available to reviewers on request |
| The retrained deciders (DAgger rounds, seed and data-volume controls) | Not released yet |

So you can run the deciders and the conveyor simulator, and measure decision time on your own machine. You cannot yet rerun the Doom studies that separate decision time from decision quality. If you need those materials for a reproduction, open an issue and tell us what you plan to do.
