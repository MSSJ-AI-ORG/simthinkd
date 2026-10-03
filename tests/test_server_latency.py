"""The HTTP server must answer fast on a kept-alive connection (regression: ~40 ms Nagle/delayed-ACK stall in 0.2.0)."""
import http.client
import statistics
import threading
import time

from simthinkd.core import Decider
from simthinkd.server import NoDelayHTTPServer, make_handler


def test_keep_alive_answers_fast():
    decider = Decider('doom-defend')
    server = NoDelayHTTPServer(('127.0.0.1', 0), make_handler(decider, 'test', 0.0))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=2)
        times = []
        for _ in range(30):
            start = time.perf_counter()
            conn.request('GET', '/health')
            conn.getresponse().read()
            times.append((time.perf_counter() - start) * 1000)
        assert statistics.median(times) < 20, times
    finally:
        server.shutdown()


if __name__ == "__main__":
    test_keep_alive_answers_fast()
    print("server latency test passed")
