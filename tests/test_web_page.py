"""Browser demo end to end: serve web/, open index.html in headless Chromium, make a decision, read the time.

    python -X utf8 tests/test_web_page.py          (needs: pip install playwright; playwright install chromium)
Checks: page loads without console errors, the example decision is TURN_LEFT, a time and the one-tick verdict
are shown, changing the enemy side to right changes the decision. Saves a screenshot to tests/.parity-data/web.png.
"""
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / 'web'))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_address[1]}/index.html'
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1100, 'height': 1300})
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(url)
        choice = lambda: page.inner_text('#choice')
        page.wait_for_function("document.getElementById('choice').textContent.length > 0", timeout=30000)
        checks.append(('enemy left at 30 degrees -> TURN_LEFT', choice() == 'TURN_LEFT'))
        median = float(page.inner_text('#timing-median').split()[0])
        checks.append((f'median decision time {median} ms fits one 28.6 ms tick', median < 28.6))
        page.select_option('#ctrl-side', 'right')
        page.wait_for_timeout(300)
        checks.append(('enemy right -> TURN_RIGHT', choice() == 'TURN_RIGHT'))
        page.select_option('#ctrl-side', 'ahead')
        page.wait_for_timeout(300)
        checks.append(('enemy ahead, gun ready -> shoots', choice().startswith('ATTACK')))
        page.screenshot(path=str(ROOT / 'tests' / '.parity-data' / 'web.png'), full_page=True)
        page.select_option('#preset', 'doom-corridor')
        page.wait_for_function("document.getElementById('situation').value.startsWith('enemies:')", timeout=30000)
        page.wait_for_timeout(500)
        checks.append(('corridor preset decides', choice() in {'MOVE_LEFT', 'MOVE_RIGHT', 'ATTACK', 'MOVE_FORWARD',
                                                                'MOVE_BACKWARD', 'TURN_LEFT', 'TURN_RIGHT'}))
        checks.append(('no console errors', not errors))
        result = {'choice': choice(), 'median': median}
        browser.close()
    server.shutdown()
    for name, ok in checks:
        print(('PASS ' if ok else 'FAIL ') + name)
    if errors:
        print('console errors:', json.dumps(errors[:5]))
    print(result)
    sys.exit(0 if all(ok for _, ok in checks) else 1)


if __name__ == '__main__':
    main()
