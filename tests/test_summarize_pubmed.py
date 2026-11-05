import asyncio
import io
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

import summarize_pubmed as app

SAMPLE = Path(__file__).resolve().parents[1] / "data/pubmed_raw.json"
CONFIG = app.Config(backoff_base=0, jitter=0)


def completion(content="A reported benefit was accompanied by nausea.", finish="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}]}


def run(records, handler, config=CONFIG):
    async def execute():
        output = io.StringIO()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            status = await app.process_records(records, output, client, config)
        return status, [json.loads(line) for line in output.getvalue().splitlines()]

    return asyncio.run(execute())


def test_sample_and_payload():
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append((request.url.path, payload))
        assert request.url.host == "192.168.1.100"
        assert request.method == "POST"
        assert payload["model"] == app.DEFAULT_MODEL
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"count": 200})
        assert payload["max_tokens"] == 128
        assert payload["temperature"] == 0
        assert payload["stream"] is False
        assert payload["n"] == 1
        assert app.INSTRUCTION in payload["messages"][1]["content"]
        assert "Do not invent findings" in payload["messages"][0]["content"]
        return httpx.Response(200, json=completion())

    status, rows = run(app.load_records(SAMPLE), handler)
    assert status == 0
    assert [r["status"] for r in rows] == ["success", "success", "skipped"]
    assert [r["pmid"] for r in rows] == ["PMID:349281", "PMID:8829102", None]
    assert rows[1]["title"] is None and rows[1]["authors"] == []
    assert rows[2]["reason"] == "missing_abstract"
    assert rows[2]["attempts"] == {"tokenize": 0, "chat": 0}
    assert [path for path, _ in calls] == ["/tokenize", "/v1/chat/completions"] * 2
    for i in (0, 2):
        assert calls[i][1]["messages"] == calls[i + 1][1]["messages"]
        assert calls[i][1]["add_generation_prompt"] is True


@pytest.mark.parametrize("raw", [None, [], "broken", 123, True])
def test_non_objects_are_skipped(raw):
    study, row = app.normalize_record(raw, 7)
    assert study is None and row["input_index"] == 7
    assert row["reason"] == "record_not_object"


@pytest.mark.parametrize("abstract", [None, "", "  \n ", [], {}, False, 10, "\ud800"])
def test_bad_abstracts_are_not_stringified(abstract):
    study, row = app.normalize_record({"abstract_text": abstract}, 0)
    assert study is None and row["reason"] == "missing_abstract"


def test_null_alias_fallback_conflicts_and_authors():
    study, row = app.normalize_record(
        {
            "id": "pmid:000123",
            "ArticleTitle": None,
            "title": "  Title\n here ",
            "abstract_text": None,
            "Abstract": " Outcome  40%. ",
            "abstract": "Other claim",
            "authorList": ["Unknown", None, 3],
            "authors": [" A ", "A", "B"],
        },
        0,
    )
    assert study == app.Study("Title here", "Outcome 40%.")
    assert row["pmid"] == "PMID:123"
    assert row["authors"] == ["A", "B"]
    assert "conflicting_abstract_text_aliases" in row["warnings"]
    assert "ignored_invalid_authorList_element" in row["warnings"]


@pytest.mark.parametrize("raw", [True, 0, -1, 1.5, "ERR_NOT_FOUND", {}, "PMID:0"])
def test_invalid_id_does_not_discard_valid_abstract(raw):
    study, row = app.normalize_record({"id": raw, "Abstract": "No benefit."}, 0)
    assert study is not None and row["pmid"] is None
    assert row["raw_id"] == raw


def test_size_bound_before_requests():
    study, row = app.normalize_record({"Abstract": "x" * (app.MAX_TEXT_BYTES + 1)}, 0)
    assert study is None and row["reason"] == "record_text_too_large"


def test_load_bom_and_whole_markdown_fence(tmp_path):
    path = tmp_path / "input.json"
    path.write_text('\ufeff```json\n[{"Abstract":"a"}]\n```', encoding="utf-8")
    assert app.load_records(path) == [{"Abstract": "a"}]


@pytest.mark.parametrize("text", ['[{"a": }]', "{}", "[NaN]", "[Infinity]"])
def test_invalid_file_rejected(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text)
    with pytest.raises(app.InputError):
        app.load_records(path)


def test_file_size_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "MAX_INPUT_BYTES", 3)
    path = tmp_path / "big.json"
    path.write_text("[{}]")
    with pytest.raises(app.InputError, match="10 MiB"):
        app.load_records(path)


@pytest.mark.parametrize(
    "failure",
    [503, 429, httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError, httpx.WriteError],
)
def test_retry_then_success(failure):
    chat_calls = 0

    def handler(request):
        nonlocal chat_calls
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"count": 10})
        chat_calls += 1
        if chat_calls == 1:
            if isinstance(failure, int):
                return httpx.Response(failure, headers={"Retry-After": "0"})
            raise failure("simulated failure", request=request)
        return httpx.Response(200, json=completion())

    status, rows = run([{"Abstract": "A"}], handler)
    assert status == 0
    assert rows[0]["attempts"] == {"tokenize": 1, "chat": 2}


def test_three_attempts_then_continue():
    def handler(request):
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"count": 10})
        if '"bad"' in json.loads(request.content)["messages"][1]["content"]:
            raise httpx.ReadTimeout("simulated timeout", request=request)
        return httpx.Response(200, json=completion())

    status, rows = run([{"Abstract": "bad"}, {"Abstract": "good"}], handler)
    assert status == 1
    assert rows[0]["reason"] == "chat_ReadTimeout_exhausted"
    assert rows[0]["attempts"]["chat"] == 3
    assert rows[1]["status"] == "success"


def test_bad_request_not_retried():
    def handler(request):
        return (
            httpx.Response(200, json={"count": 10})
            if request.url.path == "/tokenize"
            else httpx.Response(400)
        )

    status, rows = run([{"Abstract": "A"}], handler)
    assert status == 1 and rows[0]["reason"] == "chat_http_400"
    assert rows[0]["attempts"]["chat"] == 1


@pytest.mark.parametrize("http_status", [401, 403, 404, 405, 422])
def test_fatal_configuration_stops_network_but_preserves_row_accounting(http_status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(http_status)

    status, rows = run([{"Abstract": "A"}, {"Abstract": "B"}, {}], handler)
    assert status == 2 and len(calls) == 1 and len(rows) == 3
    assert rows[1]["reason"] == "not_attempted_configuration_error"
    assert rows[2]["status"] == "skipped"


@pytest.mark.parametrize("count", [3969, 4096])
def test_over_context_is_skipped_without_generation(count):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"count": count})

    status, rows = run([{"Abstract": "A"}], handler)
    assert status == 1 and calls == ["/tokenize"]
    assert rows[0]["reason"] == "context_limit_exceeded"


def test_exact_context_boundary_allowed():
    def handler(request):
        return httpx.Response(
            200, json={"count": 3968} if request.url.path == "/tokenize" else completion()
        )

    assert run([{"Abstract": "A"}], handler)[0] == 0


def test_smaller_reported_server_context_is_respected():
    status, rows = run(
        [{"Abstract": "A"}],
        lambda r: httpx.Response(200, json={"count": 2000, "max_model_len": 2048}),
    )
    assert status == 1 and rows[0]["reason"] == "context_limit_exceeded"
    assert rows[0]["attempts"]["chat"] == 0


def test_invalid_reported_context_is_configuration_error():
    status, rows = run(
        [{"Abstract": "A"}],
        lambda r: httpx.Response(200, json={"count": 100, "max_model_len": "4096"}),
    )
    assert status == 2 and rows[0]["reason"] == "tokenize_invalid_context_limit"


@pytest.mark.parametrize("count", [True, -1, 0, None, "10"])
def test_invalid_count_fails_closed(count):
    status, rows = run([{"Abstract": "A"}], lambda r: httpx.Response(200, json={"count": count}))
    assert status == 2 and rows[0]["reason"] == "tokenize_invalid_count"


@pytest.mark.parametrize(
    "data,reason",
    [
        ({}, "chat_invalid_choices"),
        ({"choices": [{}]}, "chat_incomplete_generation"),
        (completion("partial", "length"), "chat_incomplete_generation"),
        (completion(None), "chat_empty_summary"),
        (completion("  "), "chat_empty_summary"),
        (completion([]), "chat_empty_summary"),
    ],
)
def test_bad_completions(data, reason):
    def handler(request):
        return httpx.Response(200, json={"count": 10} if request.url.path == "/tokenize" else data)

    status, rows = run([{"Abstract": "A"}], handler)
    assert status == 1 and rows[0]["reason"] == reason


def test_invalid_json_and_oversized_response(monkeypatch):
    status, rows = run([{"Abstract": "A"}], lambda r: httpx.Response(200, text="<html>"))
    assert status == 1 and rows[0]["reason"] == "tokenize_invalid_json"
    monkeypatch.setattr(app, "MAX_RESPONSE_BYTES", 10)
    status, rows = run([{"Abstract": "A"}], lambda r: httpx.Response(200, text="x" * 11))
    assert status == 1 and rows[0]["reason"] == "tokenize_response_too_large"


def test_real_deadline_cancels_awaited_operation():
    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={"count": 10})

    status, rows = run([{"Abstract": "A"}], handler, replace(CONFIG, record_deadline=0.02))
    assert status == 1 and rows[0]["reason"] == "record_deadline_exceeded"
    assert rows[0]["elapsed_seconds"] < 0.5


def test_deadline_includes_retry_backoff():
    status, rows = run(
        [{"Abstract": "A"}],
        lambda r: httpx.Response(503),
        replace(CONFIG, record_deadline=0.02, backoff_base=2),
    )
    assert status == 1 and rows[0]["attempts"]["tokenize"] == 1
    assert rows[0]["reason"] == "record_deadline_exceeded"


def test_retry_after_is_honored(monkeypatch):
    sleeps = []
    calls = 0

    async def capture_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(app.asyncio, "sleep", capture_sleep)

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "5"})
        return httpx.Response(
            200, json={"count": 10} if request.url.path == "/tokenize" else completion()
        )

    assert run([{"Abstract": "A"}], handler)[0] == 0
    assert sleeps == [5]


def test_long_retry_after_does_not_retry_early():
    status, rows = run(
        [{"Abstract": "A"}], lambda r: httpx.Response(429, headers={"Retry-After": "60"})
    )
    assert status == 1 and rows[0]["reason"] == "tokenize_retry_after_exceeds_30s"
    assert rows[0]["attempts"]["tokenize"] == 1


def test_retry_after_date_and_invalid_values():
    date = format_datetime(datetime.now(UTC) + timedelta(seconds=10))
    assert 8 <= app.retry_after_seconds(date) <= 10
    for value in (None, "garbage", "NaN", "inf", "-1"):
        assert app.retry_after_seconds(value) == 0


def test_empty_or_all_invalid_input_fails_without_network():
    def forbidden(request):
        pytest.fail("invalid records must not call the server")

    assert run([], forbidden)[0] == 1
    assert run([None, {}], forbidden)[0] == 1


def test_cli_protects_input_and_existing_output(tmp_path):
    path = tmp_path / "input.json"
    path.write_text("[{}]")
    with pytest.raises(SystemExit) as exc:
        app.parse_args(["--input", str(path), "--output", str(path), "--overwrite"])
    assert exc.value.code == 2
    output = tmp_path / "results.jsonl"
    output.write_text("keep me")
    assert app.main(["--input", str(path), "--output", str(output)]) == 2
    assert output.read_text() == "keep me"


@pytest.mark.parametrize(
    "endpoint",
    [
        "ftp://x/v1/chat/completions",
        "http://user:pass@x/v1/chat/completions",
        "http://x/v1/chat/completions?q=1",
        "http://x/other",
    ],
)
def test_bad_endpoints_rejected(endpoint):
    with pytest.raises(SystemExit):
        app.parse_args(["--endpoint", endpoint])


def test_invalid_timeout_rejected():
    for value in ("0", "-1", "nan", "inf"):
        with pytest.raises(SystemExit):
            app.parse_args(["--read-timeout", value])
