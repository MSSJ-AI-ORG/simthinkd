"""HTTP server for a decider (POST /v1/systemone, GET /health). Standard library + NumPy only.

    simthinkd serve doom-defend --port 11890 [--delay-ms 0]

Binds to 127.0.0.1 by default. `--delay-ms` adds a fixed wait after inference (latency-injection experiments).
"""
import json
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import Decider


def make_handler(decider, name, delay_ms):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *unused):
            pass

        def _send(self, code, payload):
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path != '/health':
                return self._send(404, {'error': 'not found'})
            self._send(200, {'model': name, 'weights_sha256': decider.sha256, 'delay_ms': delay_ms})

        def do_POST(self):
            if self.path != '/v1/systemone':
                return self._send(404, {'error': 'not found'})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
                start = time.perf_counter()
                answers = decider.predict(body)
                infer_ms = (time.perf_counter() - start) * 1000
            except (ValueError, KeyError, TypeError) as error:
                return self._send(400, {'error': f'invalid request: {error}'})
            if delay_ms:
                time.sleep(delay_ms / 1000)
            self._send(200, {'model': name, 'answers': answers, 'usage': {'external_model_calls': 0},
                             'meta': {'total_ms': round(infer_ms + delay_ms, 3), 'infer_ms': round(infer_ms, 3),
                                      'delay_ms': delay_ms, 'weights_sha256': decider.sha256,
                                      'answered_at': datetime.now(timezone.utc).isoformat()}})

    return Handler


def serve(decider='doom-defend', host='127.0.0.1', port=11890, delay_ms=0.0, name=None):
    decider = decider if isinstance(decider, Decider) else Decider(decider)
    name = name or f'simthink-d:{decider.preset["name"]}'
    server = ThreadingHTTPServer((host, port), make_handler(decider, name, delay_ms))
    print(json.dumps({'listening': f'{host}:{port}', 'weights_sha256': decider.sha256, 'model': name}), flush=True)
    server.serve_forever()
