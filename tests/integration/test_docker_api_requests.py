"""Exercise the real SDK and entry point against a disposable Docker API stub."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.parse import parse_qs, urlsplit


def test_healthchecks_do_not_amplify_docker_api_requests():
    requests = []

    class DockerAPI(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def reply(self, value, status=200):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            path = url.path.removeprefix("/v1.47")
            query = parse_qs(url.query)
            requests.append((path, query))
            if path == "/version":
                self.reply({"ApiVersion": "1.47"})
            elif path == "/containers/json":
                self.reply([])
            elif path in ("/containers/traefik/json", "/containers/app-123/json"):
                name = path.split("/")[2]
                self.reply({
                    "Id": name, "Name": "/" + name,
                    "State": {"Status": "running", "Running": True},
                    "Config": {"Labels": {}},
                    "NetworkSettings": {"Networks": {}},
                })
            elif path == "/events":
                # Deliberately include ignored events to exercise the local guard
                # even if a server does not apply the requested filters.
                events = [
                    {"Type": "container", "Action": action, "Actor": {"ID": "health-123"}}
                    for action in ("exec_create: healthcheck", "exec_start: healthcheck", "exec_die")
                ]
                events.append({"Type": "container", "Action": "start", "Actor": {"ID": "app-123"}})
                body = b"\n".join(json.dumps(event).encode() for event in events) + b"\n"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.write(f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n")
                self.wfile.flush()
            else:
                self.reply({"message": "Unexpected API read: " + path}, status=404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), DockerAPI)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [sys.executable, "main.py", "--docker.host=tcp://127.0.0.1:" + str(server.server_port)],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    paths = [path for path, _ in requests]
    assert paths.count("/containers/traefik/json") == 2  # Startup + one lifecycle event.
    assert paths.count("/containers/app-123/json") == 1
    assert paths.count("/containers/json") == 1  # Startup scan only.
    assert "/containers/health-123/json" not in paths
    event_query = next(query for path, query in requests if path == "/events")
    assert json.loads(event_query["filters"][0]) == {
        "type": ["container"], "event": ["start", "stop", "die"],
    }
