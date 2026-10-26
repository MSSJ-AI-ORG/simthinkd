# Port notes

The two apps and placeholder images were copied byte-for-byte. `engine.py`
retains v30's teacher collection, screen features, two-level Cascade, training,
SkillTable, expected states, VerifiedRouter, DomVerifier, PopupGuard, coordinate
macros and scoring. Generic CDP methods are isolated in `cdp.py`; the private
helper import, remote endpoint, workstation guard and personal paths are removed.

`run.py` owns a local HTTP server and Chrome process, discovers Chrome, generates
mission targets for arbitrary seeds, provides a JSON command bridge, and builds
canonical summaries. The seed target generator is independently compared with
the browser app before running ERP. The scoring oracle remains teacher/scoring
input only; it does not select actions during routed or LLM mission execution.
Unexpected hand-overs without a command fail rather than simulate a model call.

Training and mission timing are separate. Fresh output directories prevent
overwriting a previous summary. Model bridge exceptions stop the invocation;
they are not counted as successful runs. No model was called for the offline
checks. Historical v30 numbers are attributed in README and not recomputed.

Not ported: SSH, workstation locks, video/screencast recording, marketing edits,
the capture-only ablation, and automatic CLI-specific model invocation. S3's new
screen-action guards are not added: this S4 port preserves the measured v30
algorithm, with existing DOM and popup guards. No new comparative performance
claim is made. Linux/macOS discovery paths are implemented but require local
execution on those platforms. No publication, push or release was performed.

An eight-seed ERP pilot collected 93 rows, but training failed because a subgroup
had too few examples for the package's train/validation/calibration split.
This failed pilot is preserved separately; it is not a successful benchmark.
Use the default 60 teacher seeds for the standard protocol.

Checks and local pilot results are recorded in the delivery CHECKS.json. The
offline suite covers file presence, four deterministic mission/plan/scoring
cases including negative outcomes, the known ERP target at seed 502, fixed-input
summary hash equality and order invariance, no-browser LLM skip, teacher/test
seed overlap rejection, and preservation of existing result files.
Additional checks exercise JSON command-bridge round trips with a local fixture
process, reject invalid actions, and reject image-oracle forbidden side effects.
These fixture processes are not LLM calls or comparative performance evidence.

Local Windows Chrome check: the default 60-seed ERP training and one seed-502
mission passed. The mission took 7.2126 seconds, with 13 decisions, zero LLM
calls, zero recorded fast misclassifications or wrong presses, and one popup
dismissal. This is one local functional check, not a speedup comparison or a
replication of all v30 groups. Raw output is retained in the internal delivery's
local_runs/erp_full60 directory. The HTTP server logged connection resets during
browser shutdown; the process exited zero, the summary recorded success, and
the owned Chrome process was no longer present after cleanup.
