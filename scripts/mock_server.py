#!/usr/bin/env python3
"""CPU-only HTTP fixture. Responses are canned; this is NOT an AI model.

python scripts/mock_server.py --port 8001
python scripts/mock_server.py --port 8001 --delay 45
python scripts/mock_server.py --port 8001 --fail-first 1 --failure drop
"""

import argparse
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "llama-3.3-70b-instruct"


def make_handler(options):
    lock = threading.Lock()
    chat_calls = 0

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if status == 429:
                self.send_header("Retry-After", "1")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected when demonstrating client cancellation/timeouts.

        def do_GET(self):
            if self.path == "/health":
                self.send_json(200, {"status": "ok", "mock": True})
            elif self.path == "/v1/models":
                self.send_json(200, {"data": [{"id": MODEL}], "mock": True})
            else:
                self.send_json(404, {"error": "mock route not found"})

        def do_POST(self):
            nonlocal chat_calls
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024 * 1024:
                    raise ValueError
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or payload.get("model") != MODEL:
                    self.send_json(404, {"error": "unknown mock model"})
                    return
            except (ValueError, TypeError):
                self.send_json(400, {"error": "invalid request"})
                return
            if self.path == "/tokenize":
                # Deliberately a fixed test fixture, NOT a real token count.
                self.send_json(
                    200, {"count": options.prompt_tokens, "max_model_len": 4096, "mock": True}
                )
                return
            if self.path != "/v1/chat/completions":
                self.send_json(404, {"error": "mock route not found"})
                return
            with lock:
                chat_calls += 1
                call_number = chat_calls
            print(f"MOCK chat attempt={call_number} delay={options.delay}s", flush=True)
            if call_number <= options.fail_first:
                if options.failure == "drop":
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.send_json(int(options.failure), {"error": "deliberate mock failure"})
                return
            time.sleep(options.delay)
            content = json.dumps(payload.get("messages", []))
            if "Drug X" in content:
                summary = (
                    "Among 500 patients, Drug X was reported to work in 40% of cases "
                    "but caused nausea."
                )
            else:
                summary = (
                    "Cohort B showed no significant improvement versus placebo, although "
                    "the abstract also states that the null hypothesis was rejected."
                )
            self.send_json(
                200,
                {
                    "id": f"mock-{call_number}",
                    "model": MODEL,
                    "mock": True,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": summary},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--delay", type=float, default=0)
    parser.add_argument("--fail-first", type=int, default=0)
    parser.add_argument("--failure", choices=("drop", "400", "429", "503"), default="503")
    parser.add_argument("--prompt-tokens", type=int, default=200)
    args = parser.parse_args()
    if args.delay < 0 or args.fail_first < 0 or args.prompt_tokens < 1:
        parser.error("delay/fail-first must be nonnegative and prompt-tokens must be positive")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args))
    print(f"MOCK ONLY - canned responses, no model - http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
