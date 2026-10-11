# Gemma 4 12B Unified — Windows 11 Laptop Experiment

**Goal:** Run `gemma-4-12B-it` locally on a Win11 laptop, validate quality for coding/reasoning tasks, and compare against the cloud 31B experiment.

**Model:** `google/gemma-4-12B-it` — 11.95B params, dense, encoder-free multimodal (text+image+audio), 256K context, sliding window attention, Apache 2.0 license.

---

## GGUF Format Explained

**GGUF (GPT-Generated Unified Format)** is a file format for storing large language models, created by the `llama.cpp` project.

**What it is:**
- A single binary file containing the model's weights, tokenizer, and metadata
- Designed for efficient loading and inference on consumer hardware

**Why it matters:**
- **Quantized weights** — models are compressed from 16-bit/32-bit floats down to 2-8 bits per weight, dramatically reducing RAM/VRAM requirements
- **CPU-friendly** — optimized for CPU inference (no GPU required), with SIMD/AVX acceleration
- **Self-contained** — one file has everything (weights + tokenizer + config), unlike HuggingFace's multi-file format

**Quantization levels (for a 12B model):**

| Quant | Bits/Weight | File Size | RAM Needed | Quality |
|-------|------------|-----------|------------|----------|
| Q3_K_M | ~3.3 | ~5 GB | ~7 GB | Low |
| Q4_K_M | ~4.7 | ~7 GB | ~10 GB | Decent |
| Q5_K_M | ~5.5 | ~8 GB | ~11 GB | Good |
| Q6_K | ~6.2 | ~10 GB | ~13 GB | Very Good |
| Q8_0 | 8 | ~12 GB | ~15 GB | Excellent |
| FP16 | 16 | ~24 GB | ~26 GB | Original |

**The `_K` variants** (Q4_K_M, Q5_K_M) use mixed-precision — important layers get more bits, less important ones get fewer. This gives better quality per bit than uniform quantization.

**GGUF vs HuggingFace format:**

| Aspect | HuggingFace | GGUF |
|--------|-------------|------|
| Files | Multiple (safetensors + tokenizer + config) | Single file |
| Precision | Full (FP16/BF16) | Pre-quantized (Q3-Q8) |
| Dependencies | `transformers` + `torch` (~2 GB) | `llama-cpp-python` (~50 MB) |
| GPU required | Recommended | Optional (CPU-optimized) |
| Best for | GPU servers, fine-tuning | Local CPU inference, edge devices |

**Bottom line for Win11 laptops:** GGUF + `llama.cpp` is the way to run LLMs on CPU. See `test_lcpp_gemma4.py` (Option 3) for the implementation.

---

## Option 0: HuggingFace Transformers (Python Script)

A test script `test_gemma4.py` is included for direct inference via the `transformers` library.

### What it does

- Loads `google/gemma-4-12B-it` using `AutoModelForCausalLM`
- **Interactive quantization selection** — choose at runtime from 5 options:

| Option | Precision | Approx VRAM/RAM | Quality | Speed |
|--------|-----------|-----------------|---------|-------|
| 0 | BF16 | ~24 GB | Best | Fastest |
| 1 | FP16 | ~24 GB | Best | Fastest |
| 2 | 8-bit | ~13 GB | Good | Moderate |
| 3 | 4-bit NF4 | ~7 GB | Decent | Slower |
| 4 | 4-bit FP4 | ~7 GB | Decent | Slower |

- Uses `apply_chat_template` for instruction-tuned conversation format
- Generates up to 1024 new tokens with sampling (temp=0.7, top_p=0.9)
- Supports optional thinking/reasoning mode (`enable_thinking=True`)
- For 4-bit/8-bit options, requires `pip install bitsandbytes`
- Script auto-detects if `bitsandbytes` is installed and warns about unavailable options
- Includes workaround for transformers 4.57.x Gemma 4 tokenizer bug (`extra_special_tokens` list vs dict)

### NF4 vs FP4 — What's the difference?

| Aspect | NF4 (NormalFloat 4) | FP4 (Floating Point 4) |
|--------|---------------------|------------------------|
| Type | Normal distribution-optimized | Standard IEEE floating point |
| How it works | Maps weights to a normal distribution, then quantizes to 4-bit | Uses 1 sign bit, 2 exponent bits, 1 mantissa bit |
| Quality | **Better** — designed for LLM weight distributions | Slightly worse — less optimal for typical weight patterns |
| Origin | Introduced in the QLoRA paper (2023) | Traditional approach, older |
| Recommendation | **Preferred default** for 4-bit | Fallback option |

**NF4 is almost always the better choice** — it was specifically designed for quantizing neural network weights and preserves more information per bit.

### ⚠️ CPU-Only Laptop Limitation

On a regular Win11 laptop **without an NVIDIA GPU**, options 2-4 (8-bit, NF4, FP4) are **not applicable**:

- `bitsandbytes` requires CUDA — it won't run on CPU-only PyTorch
- Only options 0 (BF16) and 1 (FP16) work on CPU, but need ~24 GB RAM
- For laptops with ≤16 GB RAM, the realistic path is **Option 1 (Ollama)** with GGUF quantization, which uses `llama.cpp` and supports CPU inference natively

| Your Setup | Viable Script Options | Better Alternative |
|------------|----------------------|--------------------|
| CPU-only, ≤16 GB RAM | None practical | Use Ollama (Option 1) |
| CPU-only, 24+ GB RAM | 0 (BF16) or 1 (FP16) | Ollama still faster |
| NVIDIA GPU, 8 GB VRAM | 3 (NF4) or 4 (FP4) | NF4 recommended |
| NVIDIA GPU, 16 GB VRAM | 2 (8-bit) or 3 (NF4) | 8-bit for quality |
| NVIDIA GPU, 24+ GB VRAM | 0 (BF16) or 1 (FP16) | Full precision |

### Requirements

```powershell
pip install -U transformers torch accelerate

# For 4-bit or 8-bit quantization (options 2-4):
pip install bitsandbytes
```

### ⚠️ Current Environment Discovery (Win11 Laptop)

| Package        | Version    | Notes                 |
| -------------- | ---------- | --------------------- |
| `transformers` | 4.57.6     | ✅ Available           |
| `torch`        | 2.11.0+cpu | ⚠️ **CPU-only build** |

**Critical issue:** The installed PyTorch is CPU-only (`+cpu` suffix). This means:

- **No CUDA/GPU acceleration** — inference will be extremely slow
- **Memory constraints** — Gemma 4 12B in bfloat16 needs ~24GB RAM; even with quantization, expect swapping on 16GB laptops
- **Not practical for interactive use** — a single prompt could take minutes to hours

### How to fix for GPU inference

If you have an NVIDIA GPU, install CUDA-enabled PyTorch:

```powershell
# Uninstall CPU-only torch
pip uninstall torch

# Install CUDA-enabled torch (adjust CUDA version as needed)
pip install torch --index-url https://download.pytorch.org/whl/cu126
```

Verify: `python -c "import torch; print(torch.cuda.is_available())"` should return `True`.

### Running the script

```powershell
python test_gemma4.py
```

**Recommendation:** For this laptop (CPU-only torch, likely 16GB RAM), use **Option 1 (Ollama)** with Q4_K_M quantization instead. The Transformers approach is best suited for machines with a dedicated NVIDIA GPU (16GB+ VRAM).

---

## Hardware Requirements

| RAM    | Quantization | Max Comfortable Context | Verdict                       |
| ------ | ------------ | ----------------------- | ----------------------------- |
| 8 GB   | Q4_K_M       | 4-8K                    | Tight, works for chat         |
| 16 GB  | Q4_K_M       | 32-128K                 | Comfortable                   |
| 16 GB  | Q8           | 4-8K                    | Tight, better quality         |
| 24 GB  | BF16         | 32K                     | Full precision, short context |
| 32 GB+ | BF16         | 128K+                   | Full precision, full power    |

**If your laptop has 16 GB RAM** → use Q4_K_M quantization, expect ~10 GB total memory at 128K context. This is the sweet spot.

**If your laptop has 8 GB RAM** → use Q4_K_M with short contexts (4-8K). It will work but be slow due to swap.

---

## Option 1: Ollama (Easiest — Recommended First)

### Step 1: Install Ollama

1. Download: https://ollama.com/download/windows
2. Run the installer, follow prompts
3. Open PowerShell or CMD, verify:
   
   ```
   ollama --version
   ```

### Step 2: Pull and Run the Model

```powershell
# Pull the Q4_K_M quantized model (~6 GB download)
ollama pull gemma4:12b

# Run interactively
ollama run gemma4:12b
```

**First run downloads ~6 GB.** Subsequent runs are instant.

### Step 3: Test with Your uhu Tool

```powershell
# Point uhu at local Ollama (already supports --host flag)
uhu --host http://localhost:11434 "Explain the sliding window attention in Gemma 4"
```

Or use curl directly:

```powershell
curl http://localhost:11434/api/chat -d '{
  "model": "gemma4:12b",
  "messages": [{"role": "user", "content": "Write a Python function to merge overlapping intervals"}]
}'
```

### Step 4: Test with Vision (Image Input)

```powershell
# Ollama supports multimodal for gemma4
ollama run gemma4:12b "What do you see in this image?" --image C:\path\to\image.png
```

### Step 5: Test Different Quantizations

If Q4 quality feels insufficient, try Q8 (needs ~12 GB for weights alone):

```powershell
# Check available tags at https://ollama.com/library/gemma4/tags
ollama pull gemma4:12b-q8_0    # ~12 GB download, better quality
ollama run gemma4:12b-q8_0
```

### Ollama Tips for Windows

- Ollama runs as a system service (background process)
- Models stored in: `C:\Users\<you>\.ollama\models\`
- To free disk space: `ollama rm gemma4:12b`
- To see running models: `ollama ps`
- GPU acceleration: Ollama auto-detects NVIDIA GPUs (CUDA) and uses them
- On CPU-only laptops: expect ~3-8 tok/s depending on CPU

---

## Option 2: LM Studio (GUI — Good for Exploration)

### Step 1: Install LM Studio

1. Download: https://lmstudio.ai/
2. Install and launch

### Step 2: Download Model

1. Search for `gemma-4-12b-it` in the model browser
2. Look for GGUF quantized versions (Q4_K_M recommended)
3. Download — it will show quantization options

### Step 3: Configure and Chat

1. Load the downloaded model
2. Set context length (start with 8192, increase to test limits)
3. Use the built-in chat interface for quick testing
4. LM Studio exposes an OpenAI-compatible API at `http://localhost:1234/v1`

### Step 4: Connect uhu

```powershell
uhu --host http://localhost:1234/v1 "Your prompt here"
```

### LM Studio Advantages

- Visual interface — see token count, speed, memory usage in real time
- Easy quantization switching (Q4 → Q8 → FP16 with one click)
- Built-in parameter tuning (temperature, top-p, etc.)
- Shows VRAM/RAM usage live — useful for finding your laptop's limits

---

## Option 3: llama.cpp Direct (Advanced — Maximum Control)

> **Quick start:** A Python script `test_lcpp_gemma4.py` is included that automates all of this — download, quantization selection, and inference. See details below.

### Step 1: Install

```powershell
# Via pip (includes pre-built binary)
pip install llama-cpp-python

# Or download release binary from https://github.com/ggerganov/llama.cpp/releases
# Look for llama-*-win-win64-*.zip
```

### Step 2: Download GGUF Model

Download from HuggingFace (bartowski repo, verified working):

- Q4_K_M (recommended): https://huggingface.co/bartowski/gemma-4-12B-it-GGUF/resolve/main/gemma-4-12B-it-Q4_K_M.gguf
- Other quants: https://huggingface.co/bartowski/gemma-4-12B-it-GGUF

Or use the script to auto-download (see below).

### Using `test_lcpp_gemma4.py`

The included script automates download, quantization selection, and inference:

```powershell
# Install dependencies
pip install llama-cpp-python huggingface-hub

# Auto-download Q4_K_M and run (default prompt)
python test_lcpp_gemma4.py

# Use a manually downloaded model
python test_lcpp_gemma4.py --model path\to\gemma-4-12B-it-Q4_K_M.gguf

# Interactive chat mode
python test_lcpp_gemma4.py --model path\to\model.gguf --interactive

# Choose different quantization
python test_lcpp_gemma4.py --quant Q5_K_M

# Custom prompt
python test_lcpp_gemma4.py --model model.gguf --prompt "Explain quantum computing"

# Adjust context size and threads
python test_lcpp_gemma4.py --model model.gguf --context 4096 --threads 8
```

**Key flags:**
- `--model` — Path to local .gguf file (skips download)
- `--quant` — Quantization level (Q3_K_M, Q4_K_M, Q4_K_S, Q5_K_M, Q6_K, Q8_0)
- `--context` — Context window size (default: 8192)
- `--threads` — CPU threads (default: auto-detect)
- `--interactive` — Start multi-turn chat mode
- `--max-tokens` — Max tokens to generate (default: 1024)
- `--temperature` — Sampling temperature (default: 0.7)
- `--gpu-layers` — GPU offload layers (default: 0 = CPU-only)

### Step 3: Run

```powershell
# Basic run
llama-cli -m gemma-4-12b-it-Q4_K_M.gguf -ngl 99 -c 8192 --temp 0.7

# Start OpenAI-compatible server
llama-server -m gemma-4-12b-it-Q4_K_M.gguf -ngl 99 -c 32768 --host 0.0.0.0 --port 8080

# Then connect uhu
uhu --host http://localhost:8080/v1 "Your prompt"
```

**Key flags:**

- `-ngl 99` — offload all layers to GPU (if available)
- `-ngl 0` — CPU-only mode (slower but works everywhere)
- `-c 32768` — set context window size
- `-t 8` — number of threads (match your CPU cores)
- `--mlock` — lock model in RAM (prevents swapping, if enough RAM)

---

## Benchmarks to Run

### Test 1: Basic Chat Quality

```
Prompt: "Explain the difference between MoE and dense transformer architectures. Which is better for local inference?"
Expected: Should give clear, accurate comparison. Note quality vs gemma-4-31B.
```

### Test 2: Coding — Function Implementation

```
Prompt: "Write a Python function that takes a list of intervals [[1,3],[2,6],[8,10],[15,18]] and merges overlapping ones. Include type hints and docstring."
Expected: Clean, correct implementation with proper typing.
```

### Test 3: Coding — Bug Detection

```
Prompt: "Find the bug in this code:\n\ndef fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)\n\nprint(fibonacci(-1))"
Expected: Should identify both the missing base case for negative numbers and the exponential time complexity.
```

### Test 4: Reasoning — Multi-step

```
Prompt: "A bat and ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost? Think step by step."
Expected: Should get $0.05 (not $0.10).
```

### Test 5: Long Context — Fill-the-Middle

```
Prompt: Insert a specific fact in the middle of a long document (10K+ tokens), then ask about it at the end.
Expected: Tests whether sliding window attention actually retrieves from the global layers.
```

### Test 6: Vision (if using Ollama)

```
Prompt: Feed a screenshot of your code/project and ask "What does this code do?"
Expected: Should understand layout, identify language, describe functionality.
```

---

## Performance Expectations (CPU-Only Laptop)

| Hardware           | Speed (tok/s) | Quantization | Notes                     |
| ------------------ | ------------- | ------------ | ------------------------- |
| Modern i7/i9, 16GB | 3-8           | Q4_K_M       | Usable for chat           |
| Modern i5, 16GB    | 2-5           | Q4_K_M       | Slow but functional       |
| Older CPU, 8GB     | 1-3           | Q4_K_M       | Painful, swap-heavy       |
| With NVIDIA dGPU   | 10-30+        | Q4_K_M       | GPU acceleration via CUDA |

**With NVIDIA GPU:** Ollama/LM Studio auto-detect and use CUDA. Check with:

```powershell
nvidia-smi  # Verify GPU is visible
ollama ps    # Should show GPU offload
```

---

## Troubleshooting

### "Out of memory" errors

- Reduce context: `-c 4096` or `-c 8192`
- Use smaller quantization: Q4_K_M → Q3 (if desperate)
- Close other apps (browsers, IDEs eat RAM)
- On Ollama: set `OLLAMA_NUM_PARALLEL=1` and `OLLAMA_MAX_LOADED_MODELS=1`

### Very slow inference (CPU-only)

- Reduce threads to physical cores: `-t 4` or `-t 8` (hyperthreading hurts)
- Use Q4_K_M (smallest viable quantization)
- Reduce context length

### Model not found in Ollama

```powershell
ollama list                    # See what's installed
ollama pull gemma4:12b        # Re-pull if needed
ollama run gemma4:12b --help  # See all options
```

### Windows-specific: Long path issues

If Ollama fails to download on Windows:

```powershell
# Enable long paths (run as admin)
reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1 /f
# Restart Ollama service
```

---

## Sliding Window Attention — The Catch

The 12B model's key advantage is **hybrid sliding window attention**: 40 of 48 layers use a 1024-token sliding window (evict old KV entries), while only 8 global layers keep full context. Theoretically, this means the KV cache barely grows with context length.

### Reality with Ollama/llama.cpp

Ollama uses llama.cpp under the hood. The model **runs correctly** — attention masking ensures you get the right answers. But the memory savings from KV eviction depend on implementation:

1. **Older llama.cpp versions** implemented SWA as *masking* only — tokens outside the window are ignored by attention but still stored in KV cache. **No memory savings.**

2. **Newer versions** added proper KV eviction for simple sliding window models, but Gemma 4's hybrid pattern (mixed sliding + global layers, different KV head configs per layer type) needs specific support.

3. **Current Ollama behavior** for Gemma 4 12B — likely allocates full KV cache for all layers at all positions for safety/correctness. The attention mask ensures correctness, but memory usage may be higher than the theoretical minimum.

### What This Means In Practice

| Scenario                                   | Memory at 128K context (Q4) |
| ------------------------------------------ | --------------------------- |
| Theoretical optimal (proper KV eviction)   | ~10 GB                      |
| Likely Ollama reality (full KV allocation) | ~14-18 GB                   |
| Worst case (no SWA optimization at all)    | ~14-18 GB                   |

Even in the worst case, it **still fits on a 16 GB laptop** — just with less headroom than the theoretical minimum.

### How to Verify on Your Laptop

After installing Ollama:

```powershell
# Start a chat session
ollama run gemma4:12b

# In a separate terminal, watch memory usage
# Option 1: Task Manager → Performance → Memory
# Option 2: PowerShell
Get-Process ollama* | Select-Object Name, WorkingSet64

# Send increasingly long prompts and check if memory:
#   - Plateaus → SWA eviction is working (good!)
#   - Grows linearly → no eviction, reduce context length
```

If memory grows linearly instead of plateauing, you'll need to stay under ~32K context on a 16 GB laptop instead of the theoretical 128K.

### What Actually Saves You (Regardless of SWA Implementation)

Even without perfect SWA eviction, two things reduce memory:

- **Q4 quantization** — 6 GB weights instead of 24 GB
- **GQA** (grouped query attention) — 8 KV heads instead of 16, already halves KV cache vs full MHA

So the model **will run** on a 16 GB laptop regardless. The sliding window just determines whether you get 128K context comfortably or need to stay under 32K. That's exactly what the experiment is for — find your actual hardware limit.

---

## Comparison: gemma-4-12B vs gemma-4-31B

| Metric           | 12B Unified           | 31B                   |
| ---------------- | --------------------- | --------------------- |
| Params           | 11.95B                | 30.7B                 |
| Q4_K_M weights   | ~6 GB                 | ~20 GB                |
| Runs on laptop?  | ✅ Yes                 | ❌ No (needs 64GB+)    |
| MMLU Pro         | 77.2%                 | 85.2%                 |
| LiveCodeBench v6 | 72.0%                 | 80.0%                 |
| GPQA Diamond     | 78.8%                 | 84.3%                 |
| AIME 2026        | 77.5%                 | 89.2%                 |
| Multimodal       | Text+Image+Audio      | Text+Image            |
| Context          | 256K (sliding window) | 256K (sliding window) |
| License          | Apache 2.0            | Apache 2.0            |

**The quality gap is real (~8-12% on benchmarks), but 12B is genuinely usable for coding assistance.** For quick local tasks, prototyping, and offline work, it's solid. For deep coding sessions and complex reasoning, the 31B on a proper machine is noticeably better.

---

## Recommended Experiment Flow

1. **Install Ollama** → `ollama pull gemma4:12b`
2. **Run basic chat test** → verify it works, measure tok/s on your hardware
3. **Run coding benchmarks** (Tests 2-3 above) → assess coding quality
4. **Try vision** → feed a screenshot, test multimodal
5. **Push context** → try 32K, then 64K, then 128K contexts → find your laptop's comfort zone
6. **Compare with RunPod 31B** → run same prompts, note quality difference
7. **Decide** → is 12B "good enough" for laptop use, or do you need the 31B machine?

---

## Cleanup (After Experiment)

```powershell
# Remove model to free ~6 GB disk space
ollama rm gemma4:12b

# Or keep it — it's only 6 GB
ollama list   # Check what's installed
```

---

*Created: 2025-06-19*
*Model: google/gemma-4-12B-it (Gemma 4 12B Unified)*
*Related: HUGGINGFACE-RUNPOD-EXPERIMENT.md (gemma-4-31B cloud experiment)*
