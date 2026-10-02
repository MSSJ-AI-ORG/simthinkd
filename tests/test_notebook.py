"""Execute and test the Colab quickstart notebook."""
import json
import sys
from pathlib import Path

import nbformat
from nbclient import execute


def test_notebook_executes():
    """Execute the quickstart notebook and verify key outputs."""
    notebook_path = Path(__file__).parent.parent / "notebooks" / "quickstart.ipynb"

    # Read the notebook
    with open(notebook_path, "r", encoding="utf8") as f:
        nb = nbformat.read(f, as_version=4)

    # Remove the install cell (tagged "skip-execution")
    cells_to_keep = []
    for cell in nb.cells:
        if cell.cell_type == "code":
            tags = cell.metadata.get("tags", [])
            if "skip-execution" not in tags:
                cells_to_keep.append(cell)
        else:
            cells_to_keep.append(cell)

    nb.cells = cells_to_keep

    # Execute the notebook with a 60-second timeout per cell
    print("Executing notebook...")
    try:
        executed = execute(
            nb,
            kernel_name="python",
            timeout=60,
            allow_errors=False,
        )
    except Exception as e:
        print(f"Notebook execution failed: {e}")
        raise

    # Verify key outputs
    print("\nVerifying outputs...")

    # Expected cell tags or indices for key tests
    outputs_found = {
        "one_decision": False,
        "speed_test": False,
        "train_own": False,
        "bench": False,
        "http_server": False,
    }

    for i, cell in enumerate(executed.cells):
        if cell.cell_type != "code":
            continue

        cell_id = cell.metadata.get("id", "")
        outputs = cell.get("outputs", [])

        # Check for successful output in key cells
        if cell_id == "cell_simple_decision":
            assert len(outputs) > 0, "One decision cell produced no output"
            output_text = str(outputs[-1].get("text", "") if hasattr(outputs[-1], 'get') else outputs[-1])
            assert "ATTACK" in output_text or "TURN" in output_text or "STRAFE" in output_text, \
                f"Unexpected output: {output_text}"
            outputs_found["one_decision"] = True
            print("✓ One decision cell executed")

        elif cell_id == "cell_speed_test":
            assert len(outputs) > 0, "Speed test cell produced no output"
            output_text = str(outputs[-1].get("text", "") if hasattr(outputs[-1], 'get') else outputs[-1])
            assert "Median:" in output_text and "ms" in output_text, \
                f"Speed test output missing metrics: {output_text}"
            assert "35 Hz" in output_text, "Speed test output missing tick reference"
            outputs_found["speed_test"] = True
            print("✓ Speed test cell executed")

        elif cell_id == "cell_train_own":
            assert len(outputs) > 0, "Train own cell produced no output"
            output_text = str(outputs[-1].get("text", "") if hasattr(outputs[-1], 'get') else outputs[-1])
            assert "Trained" in output_text or "HEAT" in output_text, \
                f"Training output unexpected: {output_text}"
            outputs_found["train_own"] = True
            print("✓ Train own cell executed")

        elif cell_id == "cell_bench":
            assert len(outputs) > 0, "Bench cell produced no output"
            output_text = str(outputs[-1].get("text", "") if hasattr(outputs[-1], 'get') else outputs[-1])
            assert "median" in output_text.lower() and "ms" in output_text, \
                f"Bench output missing metrics: {output_text}"
            outputs_found["bench"] = True
            print("✓ Bench cell executed")

        elif cell_id == "cell_http_server":
            assert len(outputs) > 0, "HTTP server cell produced no output"
            # Concatenate all outputs to find the HTTP decision message
            all_text = ""
            for out in outputs:
                if hasattr(out, 'get'):
                    all_text += str(out.get("text", ""))
                else:
                    all_text += str(out)
            assert "HTTP decision:" in all_text or "decision:" in all_text.lower() or "Server" in all_text, \
                f"HTTP output unexpected: {all_text}"
            outputs_found["http_server"] = True
            print("✓ HTTP server cell executed")

    # Print summary
    print("\n" + "=" * 60)
    print("NOTEBOOK TEST RESULTS:")
    print("=" * 60)
    for test_name, found in outputs_found.items():
        status = "PASS" if found else "SKIP"
        print(f"  {test_name:20s}: {status}")

    passed = sum(1 for v in outputs_found.values() if v)
    total = len(outputs_found)
    print(f"\nPassed: {passed}/{total}")

    assert passed >= 4, f"Not enough cells passed: {passed}/5"
    print("\nNotebook test PASSED ✓")


if __name__ == "__main__":
    test_notebook_executes()
