# DGX Spark: deployment and memory reasoning

This is a **documentation-supported configuration for a 128 GB DGX Spark**.
It has not been run on the employer's hardware. Client tests and mocked results
do not prove container compatibility, model accuracy, performance, or absence of
GPU OOM. Validate on the target machine before claiming those results.

## Exact proposed command

Run on the Spark whose LAN address is `192.168.1.100`. Install/configure Docker,
NVIDIA Container Toolkit, and a compatible host driver first. If the model
repository requires authentication, export an authorized `HF_TOKEN` securely.
Do not start a second server on an already occupied port.

```bash
docker run -d --name pubmed-llama \
  --platform linux/arm64 --gpus all --ipc=host \
  --ulimit memlock=-1 --ulimit stack=67108864 \
  -p 192.168.1.100:8000:8000 \
  -e HF_TOKEN \
  -e VLLM_NO_USAGE_STATS=1 \
  -e HF_HUB_DISABLE_TELEMETRY=1 \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  --entrypoint vllm \
  nvcr.io/nvidia/vllm:26.10-py3 \
  serve nvidia/Llama-3.3-70B-Instruct-FP8 \
  --served-model-name llama-3.3-70b-instruct \
  --host 0.0.0.0 --port 8000 \
  --tensor-parallel-size 1 \
  --quantization modelopt --dtype bfloat16 \
  --kv-cache-dtype auto \
  --gpu-memory-utilization 0.70 \
  --max-model-len 4096 \
  --max-num-seqs 1 \
  --max-num-batched-tokens 4096 \
  --enforce-eager \
  --generation-config vllm
```

The executable version is [../deploy/run_vllm.sh](../deploy/run_vllm.sh).
NVIDIA's release notes list vLLM 0.31.0 and CUDA 13.4.3 in release 26.10;
the tag uses NVIDIA's documented `nvcr.io/nvidia/vllm:xx.xx-py3` naming convention.
Confirm the ARM64 manifest and driver compatibility before pulling the image.
After target validation, record the exact image digest and checkpoint revision
and pin them for repeated deployment.
Sources: [release notes](https://docs.nvidia.com/deeplearning/frameworks/vllm-release-notes/rel-26-10.html),
[container conventions](https://docs.nvidia.com/deeplearning/frameworks/vllm-release-notes/running.html).

## Why this model needs quantization

Spark's Arm CPU and Blackwell GPU share **128 GB system memory**. A rough lower
estimate for 70B weights is 140 GB at BF16/FP16, 70 GB at FP8, or 35 GB at 4-bit.
Runtime memory is higher due to scales, unquantized layers, caches, activations,
loading buffers, and workspaces. The operating system also uses the same pool.
[Hardware](https://docs.nvidia.com/dgx/dgx-spark/hardware.html).

The command uses NVIDIA's **pre-quantized FP8 checkpoint**, not online conversion
of a BF16 checkpoint that could OOM while loading. `--quantization modelopt`
selects the checkpoint's loader. `--dtype bfloat16` controls remaining tensors;
it does not expand the FP8 linear weights into BF16. This plan keeps the KV cache
at the model dtype via `auto`, rather than depending on quantized-cache accuracy
or kernels. Sources: [model card](https://huggingface.co/nvidia/Llama-3.3-70B-Instruct-FP8),
[ModelOpt support](https://docs.vllm.ai/en/stable/features/quantization/modelopt/).

## How the limits work together

| Setting | Purpose |
| --- | --- |
| `--gpu-memory-utilization 0.70` | Budget the vLLM executor at 70% of reported GPU memory, leaving headroom in the shared pool; not a hard system-wide reservation. |
| `--max-model-len 4096` | Bound each prompt plus completion. |
| `--max-num-seqs 1` | Schedule at most one sequence per iteration. |
| `--max-num-batched-tokens 4096` | Bound tokens processed in one scheduling iteration. |
| `--enforce-eager` | Avoid CUDA-graph memory at the cost of some performance. |
| `--tensor-parallel-size 1` | One GPU on one Spark. |
| `max_tokens=128`, `n=1` | Bound completion work in the client payload. |

These are workload choices, not an NVIDIA certification of this particular
configuration. [Argument definitions](https://docs.vllm.ai/en/stable/configuration/engine_args/).

The Llama configuration has 80 layers, 8 KV heads, and a 128-wide head. With a
2-byte cache element, K and V require approximately:

```text
2 x 80 x 8 x 128 x 2 = 327,680 bytes per token
4,096 tokens  -> 1.25 GiB per full sequence
131,072      -> 40 GiB per full sequence
```

This arithmetic excludes allocation overhead and assumes BF16 K/V.
vLLM can reserve a larger KV pool based on its memory budget, so lowering the
context length alone does not force the whole process to use only 1.25 GiB
of cache. [Model architecture](https://huggingface.co/nvidia/Llama-3.3-70B-Instruct-FP8/blob/main/config.json).

CPU offload cannot manufacture extra physical RAM on unified memory. A tiny
completion budget also cannot make a 140 GB checkpoint fit. If FP8 still leaves
insufficient headroom in the real deployment, evaluate a supported pre-quantized
4-bit checkpoint with its matching loader/kernels and check output quality. Do
not increase the memory fraction blindly.

## Validation on the Spark

1. Inspect `uname -m`, `free -h`, `nvidia-smi`, available disk, and the current
   driver. Match the driver to the chosen image's CUDA requirements. Inspect the
   image's ARM64 manifest before downloading:
   `docker buildx imagetools inspect nvcr.io/nvidia/vllm:26.10-py3`.
2. Stop unnecessary memory-intensive workloads. Start the container, then inspect
   `docker logs -f pubmed-llama` through weight loading and warm-up. Confirm the
   logs show the quantized checkpoint and expected context/scheduling settings.
3. Check readiness and the model alias:

   ```bash
   curl --fail --max-time 5 http://192.168.1.100:8000/health
   curl --fail --max-time 5 http://192.168.1.100:8000/v1/models
   ```

4. Run the client on the sample, then a near-context-limit request. Observe system
   available memory, GPU metrics, latency, and container logs during loading,
   prefill, and generation. Save actual peak values and software/model versions
   in `docs/validation.md`. A boot alone does not verify inference safety.
5. Review the real summaries: exactly one sentence, no invented outcomes, benefit
   and nausea retained, and the second abstract's uncertainty preserved.

This command exposes the API only through the specified host LAN interface.
Use the organization's network controls. If authentication is enabled on an
existing server, supply `LLM_API_KEY` to the client. Provisioning downloads the
container and weights; inference does not call a hosted model. For an air-gapped
deployment, pre-stage the artifacts and use local paths/offline settings.

**No unconditional zero-OOM promise:** free memory, loading peaks, other processes,
and driver/kernel compatibility still matter. NVIDIA explicitly warns that
aggressive allocation can cause OOM on Spark's unified memory and recommends
lower utilization as a mitigation. [NVIDIA warning](https://docs.nvidia.com/deeplearning/frameworks/vllm-release-notes/rel-26-10.html).
