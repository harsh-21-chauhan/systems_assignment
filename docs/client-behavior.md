# Client behavior reference

For setup and commands, start with the [README](../README.md).

## Server compatibility

By default the client calls only `/v1/chat/completions`, the endpoint in the
assignment. Set `--model` (or `LLM_MODEL`) to the name configured by the server's
operator; the default matches our deployment script's served-model alias.
No model-discovery endpoint is required.

The optional `--check-tokens` flag enables vLLM's `/tokenize` check using matching
chat-template settings. If explicitly enabled, that route must work; failures
are reported rather than silently bypassed. In the default mode, the server
enforces context length and a rejected request becomes an error result without
retries for HTTP 400. Neither mode silently truncates study text. Both retain
the local text-size cap, 128 output-token limit, and sequential requests.

## What happens to the sample

| Input | Result |
| --- | --- |
| `PMID:349281` | Summarize the usable abstract; preserve the reported 40% response and nausea. |
| `8829102` | Normalize ID to `PMID:8829102`; keep missing title as `null`; summarize `Abstract`. |
| `ERR_NOT_FOUND` | Emit `skipped / missing_abstract`; make zero HTTP requests for this record. |

Titles and authors are optional. Abstract aliases are checked in order:
`abstract_text`, `Abstract`, `abstract`. A null or invalid first field does not hide
a valid fallback. Conflicting valid values generate a warning. IDs are normalized
without throwing away usable abstracts solely because their ID is invalid.

The parser accepts a UTF-8 JSON array, an optional BOM, or one outer Markdown JSON
fence. Non-object array entries and unusable abstracts are skipped individually.
Malformed JSON syntax, a non-array root, non-standard `NaN`/`Infinity`, and files
larger than 10 MiB fail clearly before requests begin. Arbitrarily broken JSON is
not guessed or repaired. Copy the supplied fixture rather than the email's
formatting backslashes.

The prompt explicitly asks:

> Summarize the clinical outcome of this study in one sentence.

It also asks the model to preserve adverse effects, uncertainty, and contradictory
source statements. The second abstract contains potentially inconsistent
statistical wording; a summary should not invent a resolution. Model prose is
not cut at the first period, which could damage decimals or abbreviations. The
one-sentence instruction and clinical fidelity still need review with the real
model; mocked summaries are not evidence of model quality.

## Slow server and connection failures

If a connection is established and the server returns a valid response after
**45 seconds**, it succeeds on the first attempt under the **90-second read
inactivity timeout**. This timeout is the maximum silence between chunks, not
the total time for an entire request. A separate `asyncio.timeout(300)` bounds all
work on one record.

Connection/timeouts, dropped connections, and HTTP 408/429/500/502/503/504 are
retried with 2-second then 4-second delays plus up to 1 second of jitter. Valid
`Retry-After` values up to 30 seconds are respected. Longer values produce an
explicit error rather than retrying earlier than the server requested. All waits
remain inside the record deadline. There are at most three attempts per operation.

Ordinary permanent HTTP errors and invalid JSON/response schemas are not retried.
Authentication, missing routes/models, and invalid tokenization configuration
stop further network calls. Remaining usable records receive
`not_attempted_configuration_error`, so normal completion still accounts for every
input. An isolated record error does not prevent later records from succeeding.

Retrying a generation POST can repeat computation when its response was lost;
there is no exactly-once guarantee. The client is sequential and the proposed
server schedules one sequence at a time. A cancelled request may take time to
release server resources.

Results are flushed after each record. Ctrl+C preserves completed rows. Logs go
to stderr and contain indexes, statuses, timings, and error codes, not full study
text or credentials. Both input and HTTP response sizes are bounded. Proxy
environment variables and redirects are disabled to keep the destination explicit.

| Exit code | Meaning |
| --- | --- |
| `0` | At least one success and no operational errors; expected invalid-data skips are recorded. |
| `1` | One or more operational errors, an I/O failure, or no successful usable records. |
| `2` | Invalid input/CLI/configuration, authentication/model route problem, or protected output exists. |
| `130` | Interrupted by the user; completed output is preserved. |

See [illustrative output](../examples/expected_results.jsonl). `input_index` is zero-based;
`attempts` separates tokenization and generation calls. The example file's
`example_only` marker and zero timings distinguish it from
measured output; actual CLI results do not contain the marker.

