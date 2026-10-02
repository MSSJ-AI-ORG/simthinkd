"""Serve Laya (open decision model by Convai Innovations, Apache 2.0, github.com/NandhaKishorM/laya) behind the same
decision request as SimThink D (POST /v1/systemone), for side-by-side timing. Same HTTP server and reply shape; only the model differs.

    LAYA_DEVICE=cpu python -X utf8 benchmarks/laya_adapter.py --port 11840

Request mapping: state.page.text (situation sentence) -> Laya state; questions.operation (choice, criteria name -> description)
-> one Laya choice question (instructions = goal sentence). The published checkpoint is used as is (Laya's router picks it).
"""
import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def model_digest():
    root = Path(os.path.expanduser('~/.cache/huggingface/hub'))
    h = hashlib.sha256()
    for p in sorted(root.rglob('*')):
        if p.is_file() and 'laya' in str(p).lower() and p.suffix in ('.safetensors', '.json'):
            h.update(p.name.encode())
            h.update(str(p.stat().st_size).encode())
    return h.hexdigest()


def to_laya(body):
    page = body.get('state', {}).get('page', {})
    q = body['questions']['operation']
    crit = {name: (v.get('description') if isinstance(v, dict) else str(v)) for name, v in q['criteria'].items()}
    ins = q.get('instructions')
    goal = ins.get('goal') if isinstance(ins, dict) else (ins or 'Which action?')
    return page.get('text', ''), {'operation': {'type': 'choice', 'instructions': goal, 'criteria': crit}}


def make_handler(router, digest):
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
            self._send(200, {'domain': 'doom', 'weights_sha256': digest, 'model': 'laya (Convai Innovations, open source)'})

        def do_POST(self):
            if self.path != '/v1/systemone':
                return self._send(404, {'error': 'not found'})
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length) or b'{}')
            start = time.perf_counter()
            state, questions = to_laya(body)
            out = router.predict(state, questions)['answers']['operation']
            elapsed = (time.perf_counter() - start) * 1000
            self._send(200, {'model': 'laya', 'answers': {'operation': {'choice': out['choice'], 'probabilities': out.get('probabilities'),
                                                                        'confidence': out.get('confidence')}},
                             'usage': {'external_model_calls': 0},
                             'meta': {'total_ms': round(elapsed, 3), 'weights_sha256': digest, 'answered_at': datetime.now(timezone.utc).isoformat()}})

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=11840)
    a = ap.parse_args()
    from laya import Router
    router = Router()
    digest = model_digest()
    server = ThreadingHTTPServer(('127.0.0.1', a.port), make_handler(router, digest))
    print(json.dumps({'listening': a.port, 'weights_sha256': digest}), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
