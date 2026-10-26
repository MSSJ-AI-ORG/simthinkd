"""Example large-model bridge for run.py --llm-cmd: one JSON request on stdin, one JSON action on stdout.

It calls the Codex CLI the way our v30 runs did (default model, reasoning effort low, one screenshot, read-only in an
empty folder) and turns its one-line answer into the JSON the runner expects. Any other model can be used by writing a
bridge with the same stdin/stdout contract.

    python run.py --app erp --cond llm --seed 502 --reps 3 --out runs/llm --llm-cmd "[\"python\", \"bridge_codex.py\"]"
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PROMPT = ("You control a web app in a browser to finish a fixed mission.\nMission: {mission}\n"
          "Your previous steps: {previous}\n"
          "Look at the attached screenshot and give the single next step as one line:\n"
          "PRESS <the exact visible label of the button, menu item or option to press>\n"
          "   (if several controls show the same label, add #N for the N-th one in reading order, e.g. PRESS Open #3)\n"
          "TYPE <the label or placeholder of the text field> := <the text to type>\n"
          "DONE   (only when the whole mission is finished and the result is showing)\n"
          "WAIT   (the page is busy; look again)\nReply with that one line only.")


def parse(out):
    lines = [l.strip().strip('`*').strip() for l in out.strip().splitlines() if l.strip()]
    for l in reversed(lines):
        m = re.match(r'^TYPE\s*[:：]?\s*(.+?)\s*:=\s*(.+)$', l, re.I)
        if m:
            return {'action': 'TYPE', 'label': m.group(1).strip().strip('"\''), 'text': m.group(2).strip().strip('"\'')}
        m = re.match(r'^PRESS\s*[:：]?\s*(.+?)$', l, re.I)
        if m:
            return {'action': 'PRESS', 'label': m.group(1).strip().strip('"\'')}
        if re.match(r'^DONE\b', l, re.I):
            return {'action': 'DONE'}
        if re.match(r'^WAIT\b', l, re.I):
            break
    return {'action': 'WAIT'}


def main():
    req = json.loads(sys.stdin.read())
    empty = Path(tempfile.gettempdir()) / 'simthinkd_bridge_empty'
    empty.mkdir(exist_ok=True)
    prompt = PROMPT.format(mission=req['mission'], previous=', '.join(req.get('previous') or []) or 'none')
    try:
        r = subprocess.run(['codex', 'exec', '--skip-git-repo-check', '-s', 'read-only', '-C', str(empty),
                            '-c', 'model_reasoning_effort=low', '-i', req['screenshot'], '-'],
                           input=prompt, capture_output=True, text=True, encoding='utf-8', timeout=170,
                           shell=(os.name == 'nt'))
        out = r.stdout
    except subprocess.TimeoutExpired:
        out = ''
    print(json.dumps(parse(out)))


if __name__ == '__main__':
    main()
