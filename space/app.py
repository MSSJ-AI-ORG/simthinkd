"""Gradio app for SimThink D: interactive decision model playground."""
import gradio as gr
import json
import statistics
import random
from pathlib import Path

import simthinkd
from simthinkd import Decider, toy


# ============================================================================
# DOOM DECIDER TAB
# ============================================================================

def decide_doom(enemy_type, side, angle, distance, enemies, sway, gun_status, ammo):
    """Tab 1: Doom defender decision."""
    # Map dropdown values to sentence parts
    enemy_map = {
        "none": None,
        "Demon": "Demon",
        "MarineChainsawVzd": "MarineChainsawVzd",
    }

    side_map = {
        "ahead": "ahead",
        "left": "left",
        "right": "right",
    }

    enemy_seen = enemy_map.get(enemy_type, "none")
    angle_str = str(int(angle))
    distance_str = str(int(distance))
    enemies_str = str(int(enemies))

    # Build the situation sentence
    if enemy_seen is None:
        state_text = f"seen: no enemy visible | enemies 0 | sway {sway} | gun {gun_status} | ammo{int(ammo)}"
    else:
        state_text = f"seen: {enemy_seen} {side_map[side]} a{angle_str} d{distance_str} | enemies {max(1, int(enemies))} | sway {sway} | gun {gun_status} | ammo{int(ammo)}"

    # Make decision
    d = Decider("doom-defend")
    result = d.decide(state_text)

    # Build output
    probs_display = {k: f"{v:.1%}" for k, v in result.probabilities.items()}

    return result.choice, json.dumps(probs_display, indent=2), f"{result.ms:.2f}"


# ============================================================================
# TRAIN YOUR OWN TAB
# ============================================================================

TRAIN_STEPS = 300


def generate_toy_examples():
    """Toy inspection examples, one 'situation => ACTION' per line."""
    return "\n".join(f"{state} => {action}" for state, action in toy.examples(3000))


def parse_training_examples(examples_text):
    """Parse 'situation => ACTION' lines; other lines are ignored."""
    examples = []
    for line in (examples_text or "").strip().split("\n"):
        if " => " in line:
            state, action = line.split(" => ", 1)
            if state.strip() and action.strip():
                examples.append((state.strip(), action.strip()))
    return examples


def train_custom(examples_text, session=None):
    """Tab 2: train a decider on the pasted examples. Returns (status, count, sample, session)."""
    import tempfile
    import time
    examples = parse_training_examples(examples_text)
    if len(examples) < 100:
        return ("Need at least 100 lines of 'situation => ACTION' (more is better).", str(len(examples)), "", session)
    names = sorted({a for _, a in examples})
    if len(names) > 8:
        return (f"At most 8 different actions; found {len(names)}.", str(len(examples)), "", session)
    is_toy = set(names) <= set(toy.ACTIONS)
    actions = {n: toy.ACTIONS[n] for n in names} if is_toy else {n: n.replace("_", " ").lower() for n in names}
    goal = toy.GOAL if is_toy else "Choose the right action for the situation."
    out = Path(tempfile.mkdtemp(prefix="simthinkd_space_")) / "decider"
    start = time.perf_counter()
    d = simthinkd.fit(examples, actions, goal=goal, out=out, steps=TRAIN_STEPS, quiet=True)
    elapsed = time.perf_counter() - start
    msg = f"Trained on {len(examples)} examples ({len(names)} actions) in {elapsed:.1f} s."
    if is_toy:
        rng = random.Random(2026)
        fresh = [toy.observe(rng) for _ in range(500)]
        agree = sum(d.decide(text).choice == toy.teacher(s) for s, text in fresh) / len(fresh)
        msg += f" Agreement with the toy teacher on 500 fresh parts: {agree:.1%}."
    sample_state = examples[0][0]
    r = d.decide(sample_state)
    sample = f"'{sample_state[:60]}' -> {r.choice} ({r.confidence:.0%}, {r.ms:.2f} ms)"
    return msg, str(len(examples)), sample, d


def decide_custom(state_text, session=None):
    """Decide with the decider trained in this browser session."""
    if session is None:
        return "No trained model yet. Train one above first.", "{}"
    if not (state_text or "").strip():
        return "Type a situation first.", "{}"
    result = session.decide(state_text)
    probs = {k: f"{v:.1%}" for k, v in result.probabilities.items()}
    return result.choice, json.dumps(probs, indent=2)


# ============================================================================
# SPEED TAB
# ============================================================================

def speed_test():
    """Tab 3: Run 1,000 decisions and measure speed."""
    d = Decider("doom-defend")
    times = []

    for _ in range(1000):
        result = d.decide("seen: Demon left a30 d5 | enemies 1 | sway left | gun ready | ammo25")
        times.append(result.ms)

    times_sorted = sorted(times)
    median = statistics.median(times_sorted)
    p95 = times_sorted[int(0.95 * len(times_sorted))]
    tick_ms = 1000.0 / 35.0
    within_tick = sum(1 for t in times if t <= tick_ms) / len(times)

    report = (
        f"Speed test: 1,000 decisions on doom-defend\n"
        f"Median: {median:.2f} ms\n"
        f"P95: {p95:.2f} ms\n"
        f"One tick at 35 Hz: {tick_ms:.1f} ms\n"
        f"Decisions within one tick: {within_tick:.1%}"
    )

    return report


# ============================================================================
# BUILD GRADIO INTERFACE
# ============================================================================

with gr.Blocks(title="SimThink D") as demo:
    gr.Markdown("# SimThink D: Fast Decision Models")
    gr.Markdown(
        "Make decisions in 1–2 ms on one CPU core. "
        "Try the bundled Doom defender, train your own on rule examples, or benchmark the speed."
    )

    with gr.Tabs():
        # ====== TAB 1: DOOM DECIDER ======
        with gr.Tab("Doom Decider"):
            gr.Markdown("## Defend the Center (ViZDoom)")
            gr.Markdown(
                "Compose a Doom situation and get the best action. "
                "Enemy type, angle, distance, ammo, and health are binned for a realistic game scenario."
            )

            with gr.Row():
                with gr.Column():
                    enemy_choice = gr.Dropdown(
                        ["none", "Demon", "MarineChainsawVzd"],
                        value="Demon",
                        label="Enemy Type"
                    )
                    side_choice = gr.Radio(
                        ["ahead", "left", "right"],
                        value="left",
                        label="Enemy Position"
                    )
                    angle_slider = gr.Slider(0, 60, step=3, value=30, label="Angle (°)")
                    distance_slider = gr.Slider(0, 20, step=1, value=5, label="Distance (m)")

                with gr.Column():
                    enemies_slider = gr.Slider(0, 3, step=1, value=1, label="Enemy Count")
                    sway_choice = gr.Radio(
                        ["idle", "left", "right"],
                        value="left",
                        label="Sway"
                    )
                    gun_status = gr.Radio(
                        ["wait", "ready"],
                        value="ready",
                        label="Gun Status"
                    )
                    ammo_slider = gr.Slider(0, 30, step=5, value=25, label="Ammo")

            with gr.Row():
                decide_button = gr.Button("Decide", size="lg")

            with gr.Row():
                with gr.Column():
                    action_output = gr.Textbox(
                        label="Chosen Action",
                        interactive=False
                    )
                with gr.Column():
                    probs_output = gr.Textbox(
                        label="Probabilities",
                        interactive=False,
                        lines=4
                    )
                with gr.Column():
                    ms_output = gr.Textbox(
                        label="Decision Time (ms)",
                        interactive=False
                    )

            decide_button.click(
                decide_doom,
                inputs=[enemy_choice, side_choice, angle_slider, distance_slider,
                        enemies_slider, sway_choice, gun_status, ammo_slider],
                outputs=[action_output, probs_output, ms_output]
            )

        # ====== TAB 2: TRAIN YOUR OWN ======
        with gr.Tab("Train Your Own"):
            gr.Markdown("## Train a Decider from Rule Examples")
            gr.Markdown(
                "Write examples in `situation => ACTION` format (one per line), or load toy inspection examples."
            )

            with gr.Row():
                gen_toy_btn = gr.Button("Load Toy Inspection Examples (3,000)")

            examples_input = gr.Textbox(
                label="Training Examples",
                lines=10,
                placeholder="part: defect none | severity minor | image clear | belt normal | rework queue short => PASS"
            )

            with gr.Row():
                train_btn = gr.Button("Train (300 steps)", size="lg")

            with gr.Row():
                status_output = gr.Textbox(label="Training Status", interactive=False)
                count_output = gr.Textbox(label="Examples Count", interactive=False)
                test_output = gr.Textbox(label="Sample Decision", interactive=False)

            gr.Markdown("### Test Your Model")
            test_input = gr.Textbox(
                label="Test Situation",
                placeholder="part: defect scratch | severity minor | image clear | belt normal | rework queue short"
            )

            with gr.Row():
                test_btn = gr.Button("Decide", size="lg")

            with gr.Row():
                test_choice = gr.Textbox(label="Predicted Action", interactive=False)
                test_probs = gr.Textbox(label="Probabilities", interactive=False, lines=4)

            gen_toy_btn.click(generate_toy_examples, outputs=[examples_input])
            session = gr.State(None)
            train_btn.click(
                train_custom,
                inputs=[examples_input, session],
                outputs=[status_output, count_output, test_output, session]
            )
            test_btn.click(
                decide_custom,
                inputs=[test_input, session],
                outputs=[test_choice, test_probs]
            )

        # ====== TAB 3: SPEED ======
        with gr.Tab("Speed"):
            gr.Markdown("## Performance Benchmark")
            gr.Markdown(
                "Run 1,000 decisions on the doom-defend model and measure latency (median, p95) "
                "and whether they fit inside one 28.6 ms game tick at 35 Hz."
            )

            speed_btn = gr.Button("Run Benchmark", size="lg")
            speed_output = gr.Textbox(
                label="Results",
                interactive=False,
                lines=6
            )

            speed_btn.click(speed_test, outputs=[speed_output])


if __name__ == "__main__":
    # For local testing: launch with default Gradio server
    demo.launch(share=False)
