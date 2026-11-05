# Validation record

Initial verification: 5 November 2026; compatibility update: 6 November 2026 (Asia/Kolkata).
Environment: macOS ARM64, Conda environment `systems-assignment`, Python 3.11.
Direct dependencies: HTTPX 0.28.1, pytest 8.3.5, Ruff 0.11.13.

## Compatibility update: 6 November

The default client now requires only `/v1/chat/completions`; `/tokenize` is
opt-in with `--check-tokens`. The model name remains configurable with `--model`
or `LLM_MODEL`, without requiring discovery calls.

- **76 unit tests passed in 0.13 s**; Ruff lint and formatting passed.
- The actual CLI used zero tokenization requests in all fast localhost checks.
- Sample: two successes and one skip, 0.09 s.
- Connection drop: recovered on generation attempt two, 2.78 s.
- HTTP 503: recovered on generation attempt two, 2.52 s.
- Real read timeout: expected error result, 0.22 s.

The original 45-second observation below predates this change; the unchanged
timeout configuration was not retested for 45 seconds in this update.

## Initial local verification: 5 November

| Check | Observed result |
| --- | --- |
| Unit tests | **71 passed in 0.12 s** after the final review. |
| Ruff lint / format | Passed. |
| Environment dependencies | `python -m pip check` reported no broken requirements. |
| Deployment shell syntax | `bash -n deploy/run_vllm.sh` passed; no container started. |
| Real localhost HTTP, sample | Two successes, one skipped record; completed in 0.12 s. |
| Connection dropped before response | Recovered on the second generation attempt in 2.46 s. |
| HTTP 503 on first generation | Recovered on the second generation attempt in 3.06 s. |
| Actual network read timeout | A 1 s delayed response with a 0.1 s read timeout and one allowed attempt produced `chat_ReadTimeout_exhausted`, exit 1, in 0.22 s. |
| Actual 45 s delayed response | Succeeded on the first generation attempt in **45.13 s**, using the default 90 s read timeout. |

The HTTP checks run the real command-line client as a separate process over
localhost TCP. The server returns canned response text and a fixed token-count
fixture. These tests establish client behavior, **not Llama quality, speed, exact
token counts, or GPU memory use**. Timings include client startup and vary by run.

Commands:

```bash
conda activate systems-assignment
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
bash -n deploy/run_vllm.sh
python scripts/verify_http.py --slow
```

## Not verified on the target system

- Reachability of the company's `192.168.1.100` endpoint.
- ARM64 image manifest/pull and host-driver compatibility.
- Loading this FP8 checkpoint and running it on an actual DGX Spark.
- Peak shared-memory/GPU usage during loading, prefill, and generation.
- Actual summaries, one-sentence compliance, and clinical fidelity from Llama.
- GitHub Actions execution on the remote repository.
- The narrated video and Unlisted YouTube upload.

Follow [infrastructure.md](infrastructure.md) for the target smoke test, and record
the image digest, model revision, driver/vLLM versions, actual memory observations,
and output here if access becomes available. Do not substitute mock results for
those measurements.
