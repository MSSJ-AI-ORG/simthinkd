#!/usr/bin/env python3
"""Web server for factory inspection viewer.

Serves static HTML and JSON results from the simulation.
"""
import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def log_message(self, format, *args):
        """Silent logging."""
        pass

    def end_headers(self):
        """Add security headers."""
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def trusted(self):
        """Check if request is from localhost."""
        hosts = (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
        return self.headers.get('Host') in hosts and self.headers.get('Origin') in (
            None, *('http://' + h for h in hosts)
        )

    def do_GET(self):
        """Handle GET requests."""
        if not self.trusted():
            return self.send_error(403)

        if self.path == '/api/result':
            result_file = Path(__file__).parent / 'result.json'
            if result_file.exists():
                try:
                    data = json.loads(result_file.read_text())
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json; charset=utf-8')
                    body = json.dumps(data).encode()
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                except Exception:
                    pass
            return self.send_error(404, 'No result available')

        if self.path == '/api/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            body = json.dumps({'status': 'ok'}).encode()
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        return super().do_GET()


def main():
    parser = argparse.ArgumentParser(description='Factory inspection web viewer')
    parser.add_argument('--port', type=int, default=8765, help='HTTP port')
    args = parser.parse_args()

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Factory Inspection Viewer: http://127.0.0.1:{args.port}', flush=True)
    print(f'(local browser only)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
