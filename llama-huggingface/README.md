# llama-huggingface — Local & Cloud LLM Experiments

Notes, scripts, and artifacts from experiments with **Gemma 4** models (Google, Apache 2.0)
via HuggingFace / GGUF / llama.cpp, plus a text-to-image side quest (Z-Image-Turbo).
Motivated by the question: *is a local 31B model good enough for agentic coding before
spending $4K+ on hardware?*

## Documents

| File | Description |
|---|---|
| `GEMMA4-31b-ANALYSIS.md` | Gemma 4 31B family overview: variants (BF16, QAT W4A16, Q4_0 GGUF), sizes, and llama-cpp-python requirements |
| `GEMMA4-31B-QUANTIZATION.md` | Deep dive into available quantizations, per-layer CPU/GPU workload breakdown, CUDA-first ecosystem notes |
| `GEMMA4-31B-RUNPOD_SETUP.md` | RunPod setup guide for downloading a ~35 GB GGUF and inspecting per-tensor metadata (CPU-only task) |
| `HUGGINGFACE-RUNPOD-EXPERIMENT.md` | Cost/quality validation plan: gemma4:31b @ 128K context on RunPod A100 (~$5–10 weekend experiment) vs buying a MacBook M5 Pro |
| `GEMMA4-WIN11-EXPERIMENT.md` | Running `gemma-4-12B-it` locally on a Win11 laptop; GGUF format explained; 12B vs 31B quality comparison plan |
| `Z-IMAGE-TURBO.md` | Deployment plan for Tongyi-MAI/Z-Image-Turbo (6B S3-DiT text-to-image) on a RunPod GPU pod |

## Scripts

| File | Description |
|---|---|
| `inspect_gguf.py` | GGUF inspector — downloads a quant from HuggingFace (or reads a local file) and prints per-tensor quantization details. `pip install huggingface-hub gguf` |
| `test_gemma4.py` | Gemma 4 12B inference via HuggingFace Transformers with quantization; includes a patch for the transformers 4.57.x `extra_special_tokens` bug |
| `test_lcpp_gemma4.py` | Gemma 4 12B via llama-cpp-python on a CPU-only Win11 laptop (GGUF) |
| `test_lcpp_gemma4_31b.py` | Same, adapted for the 31B model (mind your RAM) |
| `test_zimage.py` | Z-Image-Turbo inference on RunPod A40 (diffusers, 9 steps, guidance_scale=0) |

## Artifacts

| File | Description |
|---|---|
| `gemma4-31b-architecture.html` / `.png` | Gemma 4 31B architecture diagram (HTML source + rendered image) |
| `quant.html` | Quantization notes (HTML) |
| `gemma4-31b-ud_q8_k_xl_inspection.txt` | Captured output of `inspect_gguf.py` on the 32.6 GB `UD-Q8_K_XL` GGUF (unsloth/gemma-4-31B-it-GGUF) — full model metadata and per-tensor breakdown |

## Worked Example: Run a HuggingFace Model on a Server + Use It with uhu

👉 **`HUGGINGFACE-RUNPOD-EXPERIMENT.md`** is the end-to-end walkthrough of exactly this:
renting a GPU pod (RunPod A100), pulling `gemma4:31b` from HuggingFace, serving it
(two paths — Ollama, or raw vLLM / llama.cpp with an OpenAI-compatible API), and
connecting uhu to it from your local machine:

```bash
# Ollama path:
uhu --host http://YOUR_POD_IP:11434 --model gemma4:31b --ctx 202752

# vLLM path (OpenAI-compatible):
uhu --host http://YOUR_POD_IP:8000/v1 --model google/gemma-4-31b-it

# llama.cpp path:
uhu --host http://YOUR_POD_IP:8080 --model gemma4-31b
```

The doc also includes a cost breakdown (~$5–10 for a weekend experiment), a
Path 1 vs Path 2 comparison table, and a buy-hardware-vs-rent decision framework.

## Quick Start

```bash
pip install llama-cpp-python huggingface-hub gguf

# Inspect a quantization (downloads ~35 GB on first run)
python inspect_gguf.py --model unsloth/gemma-4-31B-it-GGUF --quant UD-Q8_K_XL

# CPU inference test (12B)
python test_lcpp_gemma4.py
```

## Key Takeaways

- **31B Q4_K_M ≈ 20 GB**, fits an A100 80GB with ~35–40 GB free at 128K context.
- **12B is the laptop option** (~6 GB quantized); compare quality against 31B before deciding.
- **CPU-only inference works but is seconds-per-token** — CUDA is effectively required for production use.
- RunPod billing is per-second; use `--cache-dir` on the large disk volume and terminate promptly.
