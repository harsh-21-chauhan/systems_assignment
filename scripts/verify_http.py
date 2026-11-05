#!/usr/bin/env python3
"""Exercise the actual CLI over local TCP using canned responses, never an LLM.

python scripts/verify_http.py          # fast socket tests
python scripts/verify_http.py --slow   # also verify an actual 45-second response
"""

import argparse
import json
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from mock_server import make_handler

ROOT = Path(__file__).resolve().parents[1]


def scenario(
    name,
    records,
    expected_exit,
    expected_statuses,
    *,
    delay=0,
    fail_first=0,
    failure="503",
    flags=(),
):
    options = SimpleNamespace(
        delay=delay, fail_first=fail_first, failure=failure, prompt_tokens=200
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(options))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="pubmed-http-") as directory:
            source = Path(directory) / "input.json"
            target = Path(directory) / "output.jsonl"
            source.write_text(json.dumps(records), encoding="utf-8")
            started = time.monotonic()
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "summarize_pubmed.py"),
                    "--input",
                    str(source),
                    "--output",
                    str(target),
                    "--endpoint",
                    f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                    *flags,
                ],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            elapsed = time.monotonic() - started
            rows = [json.loads(line) for line in target.read_text().splitlines()]
            assert completed.returncode == expected_exit, completed.stderr
            assert [r["status"] for r in rows] == expected_statuses, rows
            if name in {"connection-drop", "503-recovery"}:
                assert rows[0]["attempts"]["chat"] == 2, rows
            if name == "read-timeout":
                assert rows[0]["reason"] == "chat_ReadTimeout_exhausted", rows
                assert rows[0]["attempts"]["chat"] == 1, rows
            if name == "45-second-response":
                assert 45 <= elapsed < 85, elapsed
                assert rows[0]["attempts"]["chat"] == 1, rows
            print(
                json.dumps(
                    {
                        "test": name,
                        "passed": True,
                        "elapsed_seconds": round(elapsed, 2),
                        "statuses": expected_statuses,
                        "source": "mock HTTP, no LLM",
                    }
                ),
                flush=True,
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slow", action="store_true")
    args = parser.parse_args()
    records = json.loads((ROOT / "data/pubmed_raw.json").read_text())
    scenario("sample", records, 0, ["success", "success", "skipped"])
    scenario("connection-drop", records[:1], 0, ["success"], fail_first=1, failure="drop")
    scenario("503-recovery", records[:1], 0, ["success"], fail_first=1)
    scenario(
        "read-timeout",
        records[:1],
        1,
        ["error"],
        delay=1,
        flags=("--read-timeout", "0.1", "--max-attempts", "1"),
    )
    if args.slow:
        scenario("45-second-response", records[:1], 0, ["success"], delay=45)


if __name__ == "__main__":
    main()
