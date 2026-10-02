# Reproducing the comparison

1. Laya adapter: serves Laya (Convai Innovations, Apache 2.0) behind the same decision request.
   ```bash
   pip install laya
   LAYA_DEVICE=cpu python -X utf8 benchmarks/laya_adapter.py --port 11840
   ```
   It turns the situation sentence into Laya's `state` and the action descriptions into one `choice` question.
   Laya's own router picks the checkpoint. No training, no prompt tuning.
2. Measure both on the same 1,050 Doom states, one request at a time:
   ```bash
   simthinkd bench --name simthink-d
   simthinkd bench --url http://127.0.0.1:11840/v1/systemone --name laya
   ```
3. Live play uses ViZDoom `defend_the_center` in asynchronous mode at 35 Hz (the game does not wait for the decider).

Our run: one 6-thread workstation CPU, torch 2.14.1+cpu, laya 0.3.23, transformers 5.18.0.
