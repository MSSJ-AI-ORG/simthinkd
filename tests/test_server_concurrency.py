"""Concurrent clients must get the same answers as sequential ones, and inference must never overlap inside one process
(regression: a server fed by four parallel games died with a malloc error on 2026-10-04; inference is now serialised)."""
import http.client
import json
import threading

from simthinkd.core import Decider
from simthinkd.server import NoDelayHTTPServer, make_handler


class CountingDecider:
    """Wraps a Decider and records the largest number of predict calls running at the same time."""

    def __init__(self, inner):
        self.inner, self.sha256, self.preset = inner, inner.sha256, inner.preset
        self.active = self.peak = 0
        self.lock = threading.Lock()

    def predict(self, body):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            return self.inner.predict(body)
        finally:
            with self.lock:
                self.active -= 1


def _post(port, body):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    conn.request('POST', '/v1/systemone', json.dumps(body), {'Content-Type': 'application/json'})
    return json.loads(conn.getresponse().read())['answers']


def test_concurrent_answers_match_and_never_overlap():
    inner = Decider('doom-defend')
    body = inner.example_request() if hasattr(inner, 'example_request') else None
    decider = CountingDecider(inner)
    server = NoDelayHTTPServer(('127.0.0.1', 0), make_handler(decider, 'test', 0.0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        if body is None:
            body = {'state': {'page': {'url': 'sim://custom', 'title': '', 'text': 'enemy left'},
                              'elements': [{'id': 'A', 'role': 'button', 'label': 'A'}, {'id': 'B', 'role': 'button', 'label': 'B'}],
                              'recent_actions': []},
                    'questions': {'operation': {'type': 'choice', 'criteria': {'A': {'element': '[button] A', 'description': 'go left'},
                                                                                'B': {'element': '[button] B', 'description': 'go right'}}}}}
        expected = _post(port, body)
        results, errors = [], []

        def worker():
            try:
                for _ in range(20):
                    results.append(_post(port, body))
            except Exception as error:  # noqa: BLE001 - collected and asserted below
                errors.append(repr(error))

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors[:3]
        assert len(results) == 320
        assert all(r == expected for r in results)
        assert decider.peak == 1, decider.peak
    finally:
        server.shutdown()


if __name__ == "__main__":
    test_concurrent_answers_match_and_never_overlap()
    print("server concurrency test passed")
