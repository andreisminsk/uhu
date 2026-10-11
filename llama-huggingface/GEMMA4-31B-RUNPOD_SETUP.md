# RunPod Setup Guide for GGUF Model Inspection

## What You Need

The task is to **download a ~35 GB GGUF file and inspect its per-tensor metadata**.
This is a **CPU + storage** task — no GPU required for inspection.

If you also want to **run inference** on the model afterward, you'll need a GPU.

---

## Option A: Inspection + Quick Inference Test (Recommended)

Inspect the model and run a short inference test on a 50 GB disk.

| Setting | Value | Why |
|---------|-------|-----|
| **GPU** | 1× A100 80GB | UD-Q8_K_XL needs ~36 GB VRAM + context |
| **RAM** | 64 GB+ | System memory for offloading |
| **Disk** | 50 GB | ~35 GB model + ~5 GB OS/tools + ~1 GB mmproj + ~9 GB free |
| **Image** | RunPod PyTorch | CUDA + Python pre-installed |

### Disk Space Breakdown (50 GB)

| Item | Size |
|------|------|
| OS + Python + tools | ~5 GB |
| llama.cpp build | ~2 GB (or ~0 if using pre-built binary) |
| UD-Q8_K_XL model | ~35 GB |
| mmproj-F16 (for vision) | ~1.1 GB |
| **Free space remaining** | **~7 GB** |

### Steps

1. **Create pod** — Community Cloud → 1× A100 80GB → 50 GB disk
2. **SSH into pod** and run:

```bash
# Install dependencies
pip install huggingface-hub gguf

# Download and inspect the model (~10-15 min)
python inspect_gguf.py --model unsloth/gemma-4-31B-it-GGUF --quant UD-Q8_K_XL \
    --cache-dir /workspace/hf_cache \
    > /workspace/ud_q8_k_xl_inspection.txt 2>&1

# (Optional) Download Q8_0 for comparison — delete UD-Q8_K_XL first to free space
# rm /workspace/hf_cache/hub/models--unsloth--gemma-4-31B-it-GGUF/blobs/*
# python inspect_gguf.py --quant Q8_0 --cache-dir /workspace/hf_cache \
#     > /workspace/q8_0_inspection.txt 2>&1

# Build llama.cpp for inference
cd /workspace
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)

# Run a quick inference test (30 seconds)
MODEL_PATH=$(find /workspace/hf_cache -name "gemma-4-31B-it-UD-Q8_K_XL.gguf" | head -1)
MMPROJ_PATH=$(find /workspace/hf_cache -name "mmproj-F16.gguf" | head -1)

./build/bin/llama-cli \
    -m "$MODEL_PATH" \
    --mmproj "$MMPROJ_PATH" \
    -ngl 99 \
    -c 2048 \
    -n 128 \
    -p "Write a Python function to reverse a linked list."
```

3. **Save results** — Copy inspection files out before terminating:

```bash
# View results
cat /workspace/ud_q8_k_xl_inspection.txt

# Or download via RunPod file browser / scp
```

4. **Terminate pod** when done

### Estimated Cost
- A100 80GB: **$1.64/hr**
- Download + inspect + quick inference: ~20–30 min
- **Total: ~$0.55–0.82**

---

## Option B: Full Inference Session (Extended Testing)

If you want to spend more time chatting with the model or testing longer conversations.

| Setting | Value | Why |
|---------|-------|-----|
| **GPU** | 1× A100 80GB or 2× A100 40GB | UD-Q8_K_XL needs ~36 GB VRAM + mmproj + context |
| **RAM** | 64 GB+ | System memory for offloading if needed |
| **Disk** | 100 GB | Room for multiple quantizations + llama.cpp + context |
| **Image** | RunPod PyTorch | CUDA pre-installed |

### GPU Options by Quantization

| Quantization | Model Size | Min VRAM | Recommended GPU | RunPod Cost/hr |
|---|---|---|---|---|
| UD-IQ2_XXS | 7.95 GB | ~10 GB | RTX 3090/4090 (24 GB) | ~$0.44 |
| UD-Q4_K_XL | 17.53 GB | ~20 GB | RTX 3090/4090 (24 GB) | ~$0.44 |
| Q5_K_M | 20.17 GB | ~23 GB | RTX 3090/4090 (24 GB) | ~$0.44 |
| UD-Q5_K_XL | 20.39 GB | ~23 GB | RTX 3090/4090 (24 GB) | ~$0.44 |
| Q6_K | 23.47 GB | ~27 GB | A100 40GB | ~$1.29 |
| Q8_0 | 30.39 GB | ~34 GB | A100 40GB (tight) | ~$1.29 |
| UD-Q8_K_XL | 32.60 GB | ~36 GB | A100 80GB | ~$1.64 |

> **Note:** Add ~1.1 GB for mmproj (vision) and ~0.5 GB for MTP if used.
> Context length also consumes VRAM at runtime (~1 GB per 8K tokens for 31B).

### Steps

```bash
# 1. Install dependencies
pip install huggingface-hub gguf

# 2. Inspect the model
python inspect_gguf.py --quant UD-Q8_K_XL > inspection_results.txt 2>&1

# 3. Build llama.cpp (for inference)
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)

# 4. Run inference
./build/bin/llama-cli \
    -m ~/.cache/huggingface/hub/models--unsloth--gemma-4-31B-it-GGUF/snapshots/*/gemma-4-31B-it-UD-Q8_K_XL.gguf \
    --mmproj ~/.cache/huggingface/hub/models--unsloth--gemma-4-31B-it-GGUF/snapshots/*/mmproj-F16.gguf \
    -ngl 99 \
    -c 8192 \
    -p "Write a Python function to compute the Fibonacci sequence using memoization."
```

---

## Option C: Quick Inspection Without RunPod (Local)

If you have a machine with 50+ GB free disk but no GPU:

```bash
# Just download the imatrix file (13 MB) to see importance scores
pip install huggingface-hub gguf
huggingface-cli download unsloth/gemma-4-31B-it-GGUF imatrix_unsloth.gguf_file --local-dir .

# Then download only the specific GGUF file you want to inspect
huggingface-cli download unsloth/gemma-4-31B-it-GGUF gemma-4-31B-it-UD-Q8_K_XL.gguf --local-dir .

# Inspect
python inspect_gguf.py --local ./gemma-4-31B-it-UD-Q8_K_XL.gguf
```

---

## Tips

1. **Use `--cache-dir`** to store downloads on the large disk volume, not the default small root disk:
   ```bash
   python inspect_gguf.py --quant UD-Q8_K_XL --cache-dir /workspace/hf_cache
   ```

2. **RunPod network storage** — Downloads from HuggingFace are fast on RunPod (~500 MB/s). A 35 GB file takes ~10 min.

3. **Terminate promptly** — CPU instances are cheap but still cost money while running.

4. **Compare multiple quants** — The script caches downloads, so running it again with a different `--quant` only downloads the new file.
```
