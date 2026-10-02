---
title: SimThink D Playground
sdk: gradio
app_file: app.py
license: apache-2.0
---

# SimThink D demo (Gradio)

A small web demo of SimThink D. It has three tabs:

- **Doom decider**: describe a game situation and get an action in about 1 ms.
- **Train your own**: write a few rule examples and train a new decider in seconds.
- **Speed test**: time 1,000 decisions on your machine.

## Run it on your computer

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:7860 in your browser.

The block at the top of this file is the setting that Hugging Face Spaces reads, so this folder can also be uploaded as a Space.
