#!/usr/bin/env bash
# Run on the 128 GB DGX Spark, not on the client laptop.
# Documentation-supported baseline; validate the image, driver, and model on target hardware.
set -euo pipefail

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
