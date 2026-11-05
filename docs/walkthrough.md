# Screen-share: target 2 minutes 50 seconds

Record your own voice and screen after reviewing the code. Clearly say that the
local demo uses canned HTTP responses. Only claim a Spark test if one was actually
run. Show source, terminal output, and the deployment command; avoid credentials.

## Suggested narration and screen sequence

**0:00-0:20 - README and data/pubmed_raw.json**

"This tool reads inconsistent PubMed records and sends usable abstracts to the
company's local Llama server. It writes one JSON result per input record, including
skips and errors. The supplied sample has two usable abstracts and one missing
abstract."

**0:20-0:55 - normalize_record and select_text in summarize_pubmed.py**

"I normalize alternate field names and select the first usable string, so a null
field cannot hide a valid fallback. The second record has no title, but its
abstract is usable, so it is still summarized. The third record has a null
abstract and is skipped without an API request. Invalid IDs are preserved for
audit. Bad records do not crash processing; malformed JSON files fail clearly."

**0:55-1:25 - build_payload, Config, and process_records**

"The prompt asks for exactly one sentence and preserves reported side effects
and uncertainty. By default I use only the chat endpoint provided in the task.
I limit output to 128 tokens and send one request at a time. The server enforces
its context limit; an optional token check is available for vLLM deployments.
The read inactivity timeout is 90 seconds, so a valid response after
45 seconds succeeds on its first attempt."

**1:25-1:55 - test result and example JSONL**

"A timeout or dropped connection triggers bounded retries with backoff. There
are at most three attempts per operation and a 300-second deadline for the entire
record. An exhausted request becomes an error result, and completed results stay
on disk. These local checks use a mock HTTP server, including an actual
45-second response delay; they do not run Llama."

**1:55-2:35 - deploy/run_vllm.sh**

"The hardware trap is shared memory. The 128 GB Spark cannot hold roughly
140 GB of BF16 weights plus runtime overhead. I use a pre-quantized FP8 Llama
checkpoint, 70 percent executor memory utilization, a 4,096-token context,
one scheduled sequence, and eager execution. Limiting output tokens alone cannot
fix model-loading OOM. The exact configuration still needs startup and inference
validation on their Spark."

**2:35-2:50 - README validation and submission**

"The repository includes the single Python deliverable, deployment instructions,
tests, and reproducible mock demos. The results distinguish client verification
from hardware validation."

## Commands to prepare before recording

```bash
conda activate systems-assignment
python -m pytest -q
python scripts/verify_http.py --slow
```

Keep the successful test output visible rather than spending 45 seconds of the
recording waiting. For a live quick sample, run `mock_server.py --port 8001` in one
terminal and the README's mock client command in another. Open the resulting
`results-mock.jsonl` and show its two successes and one skip. Do not label these
canned texts as outputs from Llama.

## Upload and submission

- Keep the finished video at or below 3 minutes; target 2:50.
- Upload to YouTube and set visibility to **Unlisted**.
- Wait for processing and verify playback while signed out.
- Ensure the narration is audible and null handling and the 45-second behavior
  are stated clearly; review captions if available.
- Replace the pending video notice in README with the actual YouTube link.
- Include that link and the GitHub repository link in the submission email.
- Attach `summarize_pubmed.py` as requested, or include its direct download link
  alongside the repository link. Confirm repository visibility/access.
- The employer does not accept Loom, Drive links, or raw video attachments.

No video has been recorded or uploaded by this repository's automated tests.
