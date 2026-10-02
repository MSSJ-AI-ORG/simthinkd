# Contributing

Thanks for taking a look. Bug reports, small fixes and new examples are welcome.

## Run the tests

```bash
python -m venv .venv
.venv/bin/pip install -e ".[train]"      # on Windows: .venv\Scripts\pip install -e ".[train]"
python tests/test_package.py
```

`python tests/test_package.py --no-train` skips the training check if you do not have PyTorch.

## Pull requests

- Keep each pull request to one change.
- Add or update a test when you change behaviour.
- If you change the browser model in `web/`, run `tests/test_web_parity.py`. It checks that the JavaScript and Python models still choose the same action.

## Reporting a bug

Open an issue with the command you ran, what you expected and what happened. Include your OS and Python version.
