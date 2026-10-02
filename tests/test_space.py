"""Test the Gradio Space app functions."""
import json
import sys
from pathlib import Path

# Add the space directory to path to import app
sys.path.insert(0, str(Path(__file__).parent.parent / "space"))

# Import app functions
from app import (
    decide_doom,
    generate_toy_examples,
    parse_training_examples,
    train_custom,
    decide_custom,
    speed_test,
)

SESSION = {}


def test_decide_doom():
    """Test the Doom decider function."""
    print("Testing decide_doom...")

    # Test with a Demon
    action, probs_json, ms = decide_doom(
        enemy_type="Demon",
        side="left",
        angle=30,
        distance=5,
        enemies=1,
        sway="left",
        gun_status="ready",
        ammo=25
    )

    assert isinstance(action, str) and len(action) > 0, f"Invalid action: {action}"
    assert action in ["TURN_LEFT", "TURN_RIGHT", "ATTACK", "STRAFE_LEFT", "STRAFE_RIGHT", "ATTACK_STRAFE_LEFT", "ATTACK_STRAFE_RIGHT"], \
        f"Unknown action: {action}"

    assert action == "TURN_LEFT", f"enemy on the left at 30 degrees should give TURN_LEFT, got {action}"
    probs = json.loads(probs_json)
    assert isinstance(probs, dict) and len(probs) > 0, "Invalid probabilities"

    ms_val = float(ms)
    assert 0 < ms_val < 100, f"Unrealistic decision time: {ms_val} ms"

    print(f"  ✓ Doom decision: {action} in {ms} ms")
    print(f"  ✓ Probabilities: {list(probs.keys())[:3]}...")

    # Test with no enemy
    action2, probs2_json, ms2 = decide_doom(
        enemy_type="none",
        side="ahead",
        angle=0,
        distance=0,
        enemies=0,
        sway="idle",
        gun_status="wait",
        ammo=0
    )

    assert isinstance(action2, str) and len(action2) > 0, f"Invalid action for no enemy: {action2}"
    print(f"  ✓ No-enemy decision: {action2}")


def test_generate_toy_examples():
    """Test toy example generation."""
    print("\nTesting generate_toy_examples...")

    text = generate_toy_examples()
    assert isinstance(text, str) and len(text) > 0, "Empty examples"

    lines = text.strip().split("\n")
    assert len(lines) > 100, f"Not enough examples: {len(lines)}"

    # Verify format
    for line in lines[:3]:
        assert " => " in line, f"Invalid format: {line}"
        state, action = line.split(" => ", 1)
        assert len(state) > 0 and len(action) > 0, f"Invalid parts: {line}"

    print(f"  ✓ Generated {len(lines)} examples")
    print(f"  ✓ Sample: {lines[0][:60]}...")


def test_parse_training_examples():
    """Test parsing of training examples."""
    print("\nTesting parse_training_examples...")

    examples_text = """part: defect none | severity minor => PASS
part: defect dent | severity severe => REJECT
part: defect scratch | severity minor => REWORK"""

    examples = parse_training_examples(examples_text)
    assert len(examples) == 3, f"Expected 3 examples, got {len(examples)}"

    for state, action in examples:
        assert "part:" in state, f"Invalid state: {state}"
        assert action in ["PASS", "REJECT", "REWORK"], f"Invalid action: {action}"

    print(f"  ✓ Parsed {len(examples)} examples")
    print(f"  ✓ Sample: {examples[0]}")


def test_train_custom():
    """Train on the toy examples, then on a custom domain with its own action names."""
    print("\nTesting train_custom...")
    status, count, sample, session = train_custom(generate_toy_examples(), None)
    assert session is not None, f"no decider returned: {status}"
    assert "Agreement with the toy teacher" in status, status
    agree = float(status.split("500 fresh parts: ")[1].rstrip(".%")) / 100
    assert agree >= 0.95, f"toy agreement too low: {status}"
    SESSION["toy"] = session
    print(f"  ok {status}")

    lines = []
    for t in range(0, 40):
        for h in ("dry", "humid"):
            action = "HEAT" if t < 18 else "COOL" if t > 26 else ("FAN" if h == "humid" else "OFF")
            lines += [f"room: temp {t} | air {h} => {action}"] * 2
    status2, count2, sample2, custom = train_custom("\n".join(lines), None)
    assert custom is not None and set(custom.actions) == {"HEAT", "COOL", "FAN", "OFF"}, status2
    assert custom.decide("room: temp 5 | air dry").choice == "HEAT"
    assert custom.decide("room: temp 35 | air humid").choice == "COOL"
    SESSION["custom"] = custom
    print(f"  ok custom domain: {status2}")

    short, _, _, none = train_custom("a => B", None)
    assert none is None and "at least 100" in short


def test_decide_custom():
    """Decide with the session decider; no session -> friendly message."""
    print("\nTesting decide_custom...")
    msg, _ = decide_custom("part: defect none", None)
    assert "Train one" in msg
    action, probs_json = decide_custom("part: defect none | severity minor | image clear | belt normal | rework queue short",
                                       SESSION["toy"])
    assert action == "PASS", action
    assert isinstance(json.loads(probs_json), dict)
    print(f"  ok custom decision: {action}")


def test_speed_test():
    """Test the speed benchmark."""
    print("\nTesting speed_test...")

    result = speed_test()

    assert isinstance(result, str) and len(result) > 0, "Empty result"
    assert "Median:" in result and "ms" in result, f"Missing metrics: {result}"
    assert "35 Hz" in result, "Missing tick reference"
    assert "within one tick" in result, "Missing tick check"

    # Extract median value for verification
    lines = result.split("\n")
    for line in lines:
        if "Median:" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                try:
                    median_ms = float(parts[1].split("ms")[0].strip())
                    assert 0 < median_ms < 100, f"Unrealistic median: {median_ms}"
                    print(f"  ✓ Median latency: {median_ms:.2f} ms")
                except ValueError:
                    pass

    print(f"  ✓ Speed test result:\n{result}")


def test_all_functions_imported():
    """Verify all key functions are importable."""
    print("\nTesting imports...")

    assert decide_doom is not None
    assert generate_toy_examples is not None
    assert parse_training_examples is not None
    assert train_custom is not None
    assert decide_custom is not None
    assert speed_test is not None

    print("  ✓ All functions imported")


if __name__ == "__main__":
    print("=" * 60)
    print("SPACE APP TESTS")
    print("=" * 60)

    try:
        test_all_functions_imported()
        test_decide_doom()
        test_generate_toy_examples()
        test_parse_training_examples()
        test_train_custom()
        test_decide_custom()
        test_speed_test()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
