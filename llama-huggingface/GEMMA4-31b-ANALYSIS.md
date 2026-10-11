# Gemma 4 31B Model Analysis

## Family Overview

The Gemma 4 31B models are Google's fourth-generation multimodal AI models, released March–June 2026. All variants are licensed under Apache 2.0.

## Model Variants

| Model | Format | Params | Precision | Est. Size | Task | Downloads | Likes |
|---|---|---|---|---|---|---|---|
| **gemma-4-31B** | Safetensors | 32.68B | BF16 (full) | ~65 GB | image-text-to-text | 1.4M | 426 |
| **gemma-4-31B-it** | Safetensors | 32.68B | BF16 (full) | ~65 GB | image-text-to-text | 27.8M | 3,052 |
| **gemma-4-31B-it-qat-w4a16-ct** | Safetensors (compressed-tensors) | 33.60B | W4A16 (QAT) | ~17 GB | image-text-to-text | 578K | 29 |
| **gemma-4-31B-it-qat-q4_0-gguf** | GGUF | — | Q4_0 (QAT) | ~17 GB | image-text-to-text | 251K | 78 |
| **gemma-4-31B-it-qat-q4_0-unquantized** | Safetensors | — | BF16 (QAT intermediate) | ~65 GB | — | — | — |
| **gemma-4-31B-it-assistant** | Safetensors | 33.60B | BF16 | ~65 GB | any-to-any | 550K | 306 |

## Architecture Details

- **Base architecture (31B/31B-it):** `gemma4` — `Gemma4ForConditionalGeneration`
- **Assistant variant:** `gemma4_assistant` — any-to-any (can generate both text and images)
- **Model class:** `AutoModelForMultimodalLM` (safetensors variants), `AutoModel` (GGUF)
- **Tokenizer:** Special tokens `<bos>`, `<eos>`, `<mask>`, `<pad>`, `<unk>` with Jinja chat templates

## Quantization Options

### Q4_0 GGUF
- **Format:** GGUF (GGML Unified Format)
- **Method:** Quantization-Aware Training (QAT) with 4-bit weights
- **Compatible with:** llama.cpp, Ollama, LM Studio, KoboldCPP, text-generation-webui
- **Best for:** CPU/consumer hardware inference
- **Files:** `gemma-4-31B_q4_0-it.gguf` + `gemma-4-31B-it-mmproj.gguf` (multimodal projector)

### W4A16 Compressed Tensors
- **Format:** Safetensors with compressed-tensors format
- **Method:** QAT with 4-bit weights, 16-bit activations
- **Compatible with:** vLLM, Transformers
- **Best for:** GPU inference with reduced VRAM requirements
- **Tag:** `compressed-tensors`

### Full Precision (BF16)
- **Format:** Safetensors (2 shards for the base/it models)
- **Files:** `model-00001-of-00002.safetensors`, `model-00002-of-00002.safetensors`
- **Best for:** Maximum quality, training/fine-tuning

## Key Characteristics

- **Multimodal:** All 31B models accept images + text as input (vision-language models)
- **31B vs 12B difference:** The 12B models use `gemma4_unified` architecture and are any-to-any (can generate images), while the 31B models use `gemma4` architecture and are image-text-to-text (multimodal input, text output only) — except the `-assistant` variant which is any-to-any
- **`-it` (instruction-tuned):** Optimized for conversational/chat use — by far the most popular variant (27.8M downloads)
- **`-assistant` variant:** Uses `gemma4_assistant` architecture, supports any-to-any generation (text + image output), created April 2026
- **QAT (Quantization-Aware Training):** Models trained with quantization simulation, retaining better accuracy after quantization compared to post-training quantization methods

## Size Estimates

| Precision | Approximate Size |
|---|---|
| BF16 (full) | ~65 GB |
| W4A16 / Q4_0 (4-bit) | ~17 GB |

## Inference Script

A test script `test_lcpp_gemma4_31b.py` is available for running Gemma 4 31B IT inference via llama-cpp-python on CPU (Win11).

### Usage

```bash
# Default: Q4_0 quant, 4096 context, single-shot
python test_lcpp_gemma4_31b.py

# Interactive chat mode
python test_lcpp_gemma4_31b.py --interactive

# Specify a local model file
python test_lcpp_gemma4_31b.py --model path/to/gemma-4-31B_q4_0-it.gguf

# Choose quantization level
python test_lcpp_gemma4_31b.py --quant Q4_K_M

# Adjust context and threads
python test_lcpp_gemma4_31b.py --context 2048 --threads 8

# GPU offload (if CUDA available)
python test_lcpp_gemma4_31b.py --gpu-layers 20
```

### Key Options

| Flag | Default | Description |
|---|---|---|
| `--quant` | Q4_0 | Quantization level (Q3_K_M, Q4_0, Q4_K_M, Q4_K_S, Q5_K_M, Q6_K, Q8_0) |
| `--context` | 4096 | Context window size (lower = less RAM) |
| `--threads` | auto | CPU threads (auto-detects physical cores) |
| `--max-tokens` | 1024 | Max tokens to generate |
| `--temperature` | 0.7 | Sampling temperature |
| `--model` | auto | Path to local .gguf file (skips download) |
| `--mmproj` | auto | Path to mmproj.gguf for vision support |
| `--interactive` | off | Start interactive chat mode |
| `--gpu-layers` | 0 | GPU layers to offload (0 = CPU-only) |

### Model Sources

- **Q4_0 (official Google QAT):** `google/gemma-4-31B-it-qat-q4_0-gguf` — recommended
- **Community quants (Q3_K_M through Q8_0):** `bartowski/gemma-4-31B-it-GGUF`
- **MMPROJ (vision):** `gemma-4-31B-it-mmproj.gguf` — auto-downloaded from the official repo

### Requirements

```bash
pip install llama-cpp-python huggingface-hub
# Optional for thread detection:
pip install psutil
# For CUDA GPU support:
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu126
```

## Links

- [google/gemma-4-31B](https://hf.co/google/gemma-4-31B) — Base model
- [google/gemma-4-31B-it](https://hf.co/google/gemma-4-31B-it) — Instruction-tuned
- [google/gemma-4-31B-it-qat-q4_0-gguf](https://hf.co/google/gemma-4-31B-it-qat-q4_0-gguf) — GGUF Q4_0
- [google/gemma-4-31B-it-qat-w4a16-ct](https://hf.co/google/gemma-4-31B-it-qat-w4a16-ct) — Compressed tensors W4A16
- [google/gemma-4-31B-it-assistant](https://hf.co/google/gemma-4-31B-it-assistant) — Any-to-any assistant
