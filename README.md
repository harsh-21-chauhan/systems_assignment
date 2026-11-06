# PubMed study summarizer
## **Demo video:** [Watch the walkthrough on YouTube](https://youtu.be/x6uJ7FPcm54) — a 2-minute-53-second overview of the code, data cleaning, error handling, and local mock-server demonstration.

This Python script reads messy study records, sends usable abstracts to the
company's local AI, and saves a one-sentence summary for each study.

```text
Study records → clean the fields → ask the AI → save results
```

A missing title is allowed. A missing abstract is skipped. Slow or broken
connections are handled with timeouts and limited retries.

**Start with the local demo below.** It works on a laptop without a GPU or Llama.
The demo server returns preset answers so you can check the script's behavior.
Real AI summaries require access to the company's server.

## 1. Open the project

Prerequisite: Conda installed and available in your terminal.

For a fresh download:

```bash
git clone https://github.com/harsh-21-chauhan/systems_assignment.git
cd systems_assignment
```

If you already cloned the repository, open a terminal in that folder instead.
All commands below run from the folder containing `summarize_pubmed.py`.

## 2. Prepare Python

Run this **once** to create the environment and install dependencies:

```bash
conda env create -f environment.yml
```

If `systems-assignment` already exists, skip that command.
Activate the environment in **each terminal** you use:

```bash
conda activate systems-assignment
```

## 3. Start the demo server — Terminal 1

```bash
python scripts/mock_server.py --port 8001
```

You should see `MOCK ONLY` and `http://127.0.0.1:8001`.
**Leave this terminal running.** It acts as a practice AI server using preset
responses; it does not run a model.

## 4. Process the sample — Terminal 2

Open a second terminal in the same project folder, then run:

```bash
conda activate systems-assignment
python summarize_pubmed.py --endpoint http://127.0.0.1:8001/v1/chat/completions --input data/pubmed_raw.json --output results-mock.jsonl --overwrite
```

| Option | Purpose |
| --- | --- |
| `--endpoint` | Send requests to the demo server on your laptop. |
| `--input` | Read the three supplied study records. |
| `--output` | Save results in this file. |
| `--overwrite` | Replace the previous demo results when repeating the command. |

Expected final log:

```text
complete success=2 skipped=1 error=0
```

## 5. Read the results

In Terminal 2:

```bash
python -m json.tool --json-lines results-mock.jsonl
```

The file contains one JSON result per input record:

| Record | Expected result |
| --- | --- |
| `PMID:349281` | `success`, with a summary. |
| `8829102` | `success`, despite its missing title. |
| `ERR_NOT_FOUND` | `skipped`, with reason `missing_abstract`. |

The demo summaries are preset examples, not real Llama output.
Press **Ctrl+C in Terminal 1** when you want to stop the demo server.

## 6. Run automated checks (optional)

From the project folder with the environment active:

```bash
python -m pytest -q
python scripts/verify_http.py --slow
```

The first command runs the unit tests. The second starts its own temporary demo
servers and checks dropped connections, retries, and an actual **45-second**
delayed response. Allow about one minute. Terminal 1 is not needed for these checks.

The default read timeout allows up to **90 seconds of silence**, so a valid
response arriving after 45 seconds succeeds. Retryable failures get at most
three attempts per HTTP operation, inside a 300-second deadline per record.

## 7. Run against the real company AI server

Use this only when connected to the company's LAN/VPN and its vLLM server is ready.
The demo server is not needed for this step.

```bash
conda activate systems-assignment
python summarize_pubmed.py --endpoint http://192.168.1.100:8000/v1/chat/completions --model llama-3.3-70b-instruct --input data/pubmed_raw.json --output results-live.jsonl
python -m json.tool --json-lines results-live.jsonl
```

The model name must match the name configured on the server. Our Docker command
sets it to `llama-3.3-70b-instruct`. If the company uses another name, replace the
value after `--model` with the name they provide (or inspect `/v1/models` if available).
The script does not require a model-discovery endpoint.

**By default, only the supplied `/v1/chat/completions` endpoint is used.**
If the server also supports vLLM's `/tokenize`, you can optionally add
`--check-tokens` to reject oversized prompts before generation. Without that
option, the server enforces its context limit and any rejection is saved as an
error; input is never silently truncated. The local text-size cap, 128 output-token
limit, and sequential requests remain in effect in both modes.
If authentication is enabled, set `LLM_API_KEY` in your environment.
For another run, use a new output filename or explicitly add `--overwrite`.

**Server setup is a separate task on the DGX Spark.** If the server is already
running, use it. Otherwise, its operator should follow the prerequisites in
[infrastructure.md](docs/infrastructure.md), then run:

```bash
bash deploy/run_vllm.sh
```

That file contains the exact proposed Docker command. It uses a pre-quantized
model and memory/workload limits to reduce OOM risk. Actual Spark validation is
still required; the laptop demo cannot verify GPU memory behavior.

## Common setup problems

| Message or problem | Fix |
| --- | --- |
| `conda: command not found` | Install/initialize Conda, then reopen the terminal. |
| Conda environment already exists | Skip creation and run `conda activate systems-assignment`. |
| `conda activate` asks for initialization | On macOS's default shell, run `conda init zsh`, reopen the terminal, then activate. |
| `No module named httpx` or `pytest` | Activate the environment, then run `python -m pip install -r requirements-dev.txt`. |
| Script/input file not found | Change into the cloned `systems_assignment` folder first. |
| Demo connection fails | Keep Terminal 1 running and use port `8001` in both commands. |
| Port `8001` is already in use | Stop the previous demo with Ctrl+C, or change the port in both commands. |
| Output already exists | Choose a new filename or add `--overwrite` to replace it. |

## Submission files and details

- [summarize_pubmed.py](summarize_pubmed.py): the Python deliverable.
- [deploy/run_vllm.sh](deploy/run_vllm.sh): exact proposed server launch command.
- [Infrastructure explanation](docs/infrastructure.md): memory reasoning and target checks.
- [Client behavior](docs/client-behavior.md): cleaning rules, retries, and exit codes.
- [Validation results](docs/validation.md): what was tested locally and what remains unverified.
- [Walkthrough script](docs/walkthrough.md): recording guide for the required video.
- [Original solution PDF](output/pdf/solution-plan.pdf): design and repository diagram.

The employer also requires a narrated screen-share of at most three minutes,
uploaded to YouTube as **Unlisted**, with its link in the submission email.
