# Factory inspection twin

A simulated inspection conveyor. Each part passes a camera, and a decision must arrive within 400 ms, before the part reaches the diverter. A SimThink D decider makes that decision.

This is the second environment of the paper ([docs/FIGURES.md](../../docs/FIGURES.md)).

## What it does

- Makes parts with real defects (scratch, dent, missing fastener, stain) and adds camera noise.
- Sends each part's description to the decider over HTTP and waits at most until the deadline.
- Routes the part: pack, scrap, rework, or hold for a person.
- Reports throughput, defects that slipped through, good parts thrown away, late decisions, decision time and cost.

The simulator and the viewer use only the Python standard library. The decider needs `simthinkd`.

## Quick start

Run these from this folder.

1. Train a decider from the simulator's own rules. This takes seconds on a CPU.

   ```bash
   pip install "simthinkd[train]"
   python train_inspection_decider.py --out models/factory_inspection
   ```

2. Start the decider in a second terminal.

   ```bash
   simthinkd serve models/factory_inspection --port 11890
   ```

3. Run 100 parts against it.

   ```bash
   python run.py --arm D --parts 100 --timing live
   ```

   It reads the decider's weight hash from the server, then prints the results and saves them to `result.json`.

4. Look at the results in a browser.

   ```bash
   python server.py --port 8765
   ```

   Then open http://127.0.0.1:8765.

On our test PC, step 1 took 6 seconds. Step 3 gave 88% correct decisions, no late decisions and a median decision time of 20 ms. With these default settings 9.1% of defective parts still slipped through, so train with more parts (`--parts`) or more steps (`--steps`) before you rely on it.

## Who decides

| Arm | Decision made by |
|---|---|
| T0 | The simulator's own rules, with no delay. Use it as the baseline. |
| S | The same rules, with an added delay. |
| D | The SimThink D decider on this computer. |
| J | A second decider at `--slow-url`, for example a slower model on another machine. |
| CASCADE | D first. If D is not sure (below `--tau`), ask J. |
| RANDOM | A random choice, for comparison. |

## Options

```bash
python run.py --arm D --parts 100 --seed 910000 --line line_B --belt-speed 1.0 --defect-rate 0.08 --timing live
```

- `line_A`: one product family.
- `line_B`: mixed families with a packing buffer.

## Limits

- The simulation runs as fast as the computer allows. It is not tied to a real clock.
- A late decision is counted as late, and the part is still routed.
- There is no real equipment or PLC.
- Results depend on the trained decider. Train again if you change the rules.
