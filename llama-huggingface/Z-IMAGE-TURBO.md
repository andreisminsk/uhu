# Z-Image-Turbo on RunPod — Deployment Plan

> **Goal**: Run Tongyi-MAI/Z-Image-Turbo (6B param text-to-image model) on a RunPod GPU pod to generate photorealistic images.

---

## 1. Model Overview

- **Model**: Z-Image-Turbo by Tongyi-MAI (Alibaba)
- **Architecture**: Scalable Single-Stream DiT (S3-DiT), 6B parameters
- **Text Encoder**: Qwen3 (2.6B, 36 layers, 2560 hidden)
- **VAE**: AutoencoderKL (16 latent channels)
- **Pipeline**: `ZImagePipeline` (Diffusers)
- **Inference**: 8 NFE (num_inference_steps=9), guidance_scale=0.0
- **Resolution**: 512×512 up to 2048×2048 (any aspect ratio)
- **License**: Apache 2.0
- **HF**: https://huggingface.co/Tongyi-MAI/Z-Image-Turbo

### Model Weights Size

| Component | Size |
|---|---|
| Transformer (DiT) | 22.93 GB |
| Text Encoder (Qwen3) | 6.98 GB |
| VAE | 0.16 GB |
| **Total download** | **~30 GB** |
| **VRAM at bfloat16** | **~30 GB** |
| **VRAM with inference overhead** | **~34-36 GB** |

---

## 2. RunPod Pod Setup

### Minimum Hardware

| GPU | VRAM | Cost (Community) | Notes |
|---|---|---|---|
| A40 | 48 GB | ~$0.49/hr | ✅ Best value — fits easily with headroom |
| A100 (40GB) | 40 GB | ~$1.14/hr | ⚠️ Tight — may need CPU offloading |
| A100 (80GB) | 80 GB | ~$1.39/hr | ✅ Overkill, plenty of headroom |
| RTX A6000 | 48 GB | ~$0.76/hr | ✅ Works fine |

**Recommended**: A40 Community ($0.49/hr) — cheapest option that fits the model.

### Create Pod

1. Go to https://runpod.io → **Deploy** → **GPU Cloud**
2. Select **A40** (or A100 80GB if A40 unavailable)
3. **Template**: `RunPod PyTorch` (official, includes CUDA + PyTorch)
4. **Storage**: Set **Container Disk** to at least **50 GB** (model is ~30 GB download)
5. **Volume**: Mount `/workspace` to a Network Volume (persists between pod restarts) — recommended
6. **Expose HTTP Ports**: 8888 (for Jupyter/gradio if needed)
7. Click **Deploy**

### Verify GPU

```bash
nvidia-smi
# Should show A40 with 48GB VRAM
```

---

## 3. Install Dependencies

```bash
# Update pip
pip install --upgrade pip

# Install diffusers from source (required for ZImagePipeline)
pip install git+https://github.com/huggingface/diffusers

# Install other dependencies
pip install transformers accelerate sentencepiece
```

> ⚠️ **Do NOT use `pip install diffusers`** — the PyPI version may not yet include `ZImagePipeline`. Install from source.

### Verify Install

```bash
python3 -c "from diffusers import ZImagePipeline; print('ZImagePipeline OK')"
```

---

## 4. Download Model

### Option A: Auto-download (first run)

The model downloads automatically on first `from_pretrained()` call. ~30 GB download, takes 5-15 min depending on bandwidth.

### Option B: Pre-download to /workspace (recommended)

```bash
pip install -U huggingface_hub

# Download to persistent workspace storage
HF_HUB_ENABLE_HF_TRANSFER=1 huggingface-cli download Tongyi-MAI/Z-Image-Turbo --local-dir /workspace/models/Z-Image-Turbo
```

> Set `HF_HUB_ENABLE_HF_TRANSFER=1` for faster downloads (uses Rust-based parallel downloader).

### Using Pre-downloaded Model

```python
pipe = ZImagePipeline.from_pretrained(
    "/workspace/models/Z-Image-Turbo",  # local path instead of HF repo ID
    torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=False,
)
```

---

## 5. Run Inference

### Basic Generation Script

```python
#!/usr/bin/env python3
"""Z-Image-Turbo inference on RunPod A40"""

import torch
from diffusers import ZImagePipeline

# Load pipeline
pipe = ZImagePipeline.from_pretrained(
    "Tongyi-MAI/Z-Image-Turbo",
    torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=False,
)
pipe.to("cuda")

# Optional: Flash Attention 2 (faster on A40)
# pipe.transformer.set_attention_backend("flash")

# Optional: torch.compile for faster repeated inference
# First run will be slow due to compilation
# pipe.transformer.compile()

prompt = "Photorealistic image of an elderly man riding a sleek black motorcycle on a winding mountain road carved into a steep rock face. The man has a long grey beard flowing under his helmet, long silver-grey hair, and wears dark sunglasses. Towering mountain walls rise on one side, densely covered with lush hanging green plants, vines, and ferns draping over wet stone. On the other side, a rushing mountain river flows alongside the road, with multiple waterfalls cascading down the rocky cliffs into the river below. Mist from the waterfalls catches the light. The road curves dramatically through the gorge. Dramatic natural lighting, golden hour sun rays breaking through the mountain gap, wet road surface reflecting the sky. Shot on Sony A7R IV, 24mm wide angle, f/8, deep depth of field, ultra-realistic, National Geographic quality, 8K detail."

# Generate
image = pipe(
    prompt=prompt,
    height=1024,
    width=1024,
    num_inference_steps=9,   # = 8 DiT forwards (Turbo model)
    guidance_scale=0.0,       # MUST be 0 for Turbo models
    generator=torch.Generator("cuda").manual_seed(42),
).images[0]

image.save("/workspace/z_image_output.png")
print(f"Saved to /workspace/z_image_output.png")
```

### Key Parameters

| Parameter | Turbo Value | Notes |
|---|---|---|
| `num_inference_steps` | 9 | Results in 8 DiT forward passes |
| `guidance_scale` | 0.0 | **Must be 0** for Turbo (no CFG) |
| `height` / `width` | 512–2048 | Any aspect ratio, total pixels flex |
| `torch_dtype` | `torch.bfloat16` | Best on modern GPUs |
| `generator` | `manual_seed(N)` | For reproducibility |

---

## 6. Performance Optimizations

### Flash Attention 2 (Recommended on A40)

```bash
pip install flash-attn --no-build-isolation
```

```python
pipe.transformer.set_attention_backend("flash")
```

### torch.compile (Faster After Warmup)

```python
# First inference takes ~2-5 min for compilation, then ~30-50% faster
pipe.transformer.compile()
```

### CPU Offloading (For VRAM < 40GB)

```python
# If VRAM is tight (e.g., A100 40GB), offload to CPU between steps
pipe.enable_model_cpu_offload()
```

### Quantization (For 16-24GB VRAM)

If running on a smaller GPU, you can use quantization to fit in ~16GB VRAM:

```python
from diffusers import ZImagePipeline, BitsAndBytesConfig

nf4_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
)

pipe = ZImagePipeline.from_pretrained(
    "Tongyi-MAI/Z-Image-Turbo",
    quantization_config=nf4_config,
    torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=True,
)
# No .to("cuda") needed — quantized model auto-loads to GPU
```

---

## 7. Batch Generation Script

```python
#!/usr/bin/env python3
"""Batch image generation with Z-Image-Turbo"""

import torch
from diffusers import ZImagePipeline
import os

OUTPUT_DIR = "/workspace/z_image_outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

pipe = ZImagePipeline.from_pretrained(
    "Tongyi-MAI/Z-Image-Turbo",
    torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=False,
)
pipe.to("cuda")

# Optional speedups
pipe.transformer.set_attention_backend("flash")

prompts = [
    "Photorealistic elderly man on black motorcycle, mountain gorge, waterfalls, lush green plants on rock walls, golden hour lighting",
    "Aerial view of a winding mountain road beside a rushing river, dramatic cliffs with hanging vegetation, misty waterfalls",
    "Close-up portrait of a bearded biker with sunglasses on a mountain road, waterfall in background, photorealistic 8K",
]

for i, prompt in enumerate(prompts):
    image = pipe(
        prompt=prompt,
        height=1024,
        width=1024,
        num_inference_steps=9,
        guidance_scale=0.0,
        generator=torch.Generator("cuda").manual_seed(i),
    ).images[0]
    
    path = os.path.join(OUTPUT_DIR, f"output_{i:03d}.png")
    image.save(path)
    print(f"Saved: {path}")

print("Done! All images generated.")
```

---

## 8. Web UI (Gradio)

To generate images from a browser instead of SSH:

```python
#!/usr/bin/env python3
"""Gradio web UI for Z-Image-Turbo on RunPod"""

import torch
import gradio as gr
from diffusers import ZImagePipeline

pipe = ZImagePipeline.from_pretrained(
    "Tongyi-MAI/Z-Image-Turbo",
    torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=False,
)
pipe.to("cuda")
pipe.transformer.set_attention_backend("flash")

def generate(prompt, seed, width, height):
    generator = torch.Generator("cuda").manual_seed(int(seed))
    image = pipe(
        prompt=prompt,
        height=height,
        width=width,
        num_inference_steps=9,
        guidance_scale=0.0,
        generator=generator,
    ).images[0]
    return image

demo = gr.Interface(
    fn=generate,
    inputs=[
        gr.Textbox(label="Prompt", lines=3),
        gr.Number(label="Seed", value=42),
        gr.Slider(512, 2048, step=128, value=1024, label="Width"),
        gr.Slider(512, 2048, step=128, value=1024, label="Height"),
    ],
    outputs=gr.Image(type="pil"),
    title="Z-Image-Turbo",
)

demo.launch(server_name="0.0.0.0", server_port=8888)
```

Access at: `https://<POD_ID>-8888.proxy.runpod.net`

---

## 9. Troubleshooting

### ❌ `mlx runner failed: failed to load MLX`

**Cause**: You installed the Ollama MLX version (`x/z-image-turbo:bf16`), which only runs on Apple Silicon.

**Fix**: Use the Diffusers pipeline instead (see Section 5). Remove the Ollama model:
```bash
ollama rm x/z-image-turbo:bf16
```

### ❌ `ImportError: cannot import name 'ZImagePipeline'`

**Cause**: PyPI `diffusers` package doesn't include ZImagePipeline yet.

**Fix**: Install from source:
```bash
pip install git+https://github.com/huggingface/diffusers
```

### ❌ `CUDA out of memory`

**Fixes** (try in order):
1. Use CPU offloading: `pipe.enable_model_cpu_offload()`
2. Use 4-bit quantization (Section 6)
3. Switch to larger GPU (A100 80GB)

### ❌ Slow first inference

**Normal**: First run involves CUDA kernel compilation and model loading. Subsequent runs are fast (~5-15 sec for 1024×1024 on A40).

### ❌ `flash-attn` build fails

```bash
pip install flash-attn --no-build-isolation
# If that fails, skip it — SDPA (default) works fine, just slightly slower
```

---

## 10. Cost Estimates

| GPU | VRAM | Cost/hr | Cost/image (est.) | Notes |
|---|---|---|---|---|
| A40 | 48 GB | $0.49 | ~$0.002 | Best value |
| A100 80GB | 80 GB | $1.39 | ~$0.004 | Overkill but fast |
| A6000 | 48 GB | $0.76 | ~$0.003 | Same VRAM as A40 |

Assuming ~15-30 sec per 1024×1024 image after model load.

---

## 11. Quick-Start Checklist

- [ ] Deploy RunPod pod with A40 GPU, 50GB+ disk, PyTorch template
- [ ] SSH into pod, verify `nvidia-smi` shows GPU
- [ ] `pip install git+https://github.com/huggingface/diffusers transformers accelerate sentencepiece`
- [ ] `pip install flash-attn --no-build-isolation` (optional, faster)
- [ ] Create and run generation script (Section 5)
- [ ] First run downloads ~30 GB model, then generates image
- [ ] Retrieve image: `scp root@<pod-ip>:/workspace/z_image_output.png .` or use RunPod file browser

---

## 12. Why NOT Ollama

The Ollama version (`x/z-image-turbo:bf16`) is packaged with **MLX** (Apple Metal) backend — it **only runs on Apple Silicon Macs**. The model itself is a standard Diffusers pipeline that runs on any CUDA GPU via PyTorch. Using the native Diffusers pipeline gives you:

- Full control over parameters (steps, CFG, seed, resolution)
- Flash Attention support
- Quantization options for smaller GPUs
- Batch generation
- Gradio web UI
- No 500 errors

---

## 13. How It All Works

This section explains the full pipeline — from loading the model to saving the final image — and the key concepts that make it possible.

### Step-by-Step: What the Script Does

#### 1. Imports

```python
import torch
from diffusers import ZImagePipeline
```

- **`torch`** — PyTorch, the deep learning framework. Needed for `torch.bfloat16` dtype and CUDA device management.
- **`ZImagePipeline`** — A specialized diffusers pipeline class for Z-Image-Turbo. Orchestrates the full text-to-image flow: text encoding → diffusion → VAE decoding.

#### 2. Loading the Model

```python
pipe = ZImagePipeline.from_pretrained(
    "Tongyi-MAI/Z-Image-Turbo",
    torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=False,
)
```

**Where the model comes from:**

`"Tongyi-MAI/Z-Image-Turbo"` is a **HuggingFace Hub repository ID**. `from_pretrained()` contacts `https://huggingface.co/Tongyi-MAI/Z-Image-Turbo` and downloads the model files.

**What gets downloaded (~30 GB total):**

| File | Size | Purpose |
|---|---|---|
| `transformer/diffusion_pytorch_model.safetensors` | ~22.9 GB | The core DiT diffusion model |
| `text_encoder/model.safetensors` | ~7 GB | Qwen3 text encoder — tokenizes and embeds your prompt |
| `vae/diffusion_pytorch_model.safetensors` | ~160 MB | Decodes latent space back to pixels |
| `tokenizer/` files | Small | Tokenizes text for the encoder |
| `scheduler/scheduler_config.json` | Small | Defines the 8-step inference schedule |
| `model_index.json` | Small | Tells diffusers which components to wire together |

**Caching:** Files are downloaded once to `~/.cache/huggingface/hub/models--Tongyi-MAI--Z-Image-Turbo/`. Subsequent runs load from cache.

**`torch_dtype=torch.bfloat16`:** All weights are loaded in **bfloat16** (16-bit brain float). This halves memory vs float32 (~30 GB instead of ~60 GB) with negligible quality loss on Ampere+ GPUs (A40, A100).

**`low_cpu_mem_usage=False`:** Disables the "load on CPU first, then move to GPU" pattern. Since the A40 has 48 GB VRAM, the model loads directly into GPU memory without the slower CPU staging. Faster, but requires enough VRAM.

#### 3. Moving to GPU

```python
pipe.to("cuda")
```

Moves all pipeline components (transformer, text encoder, VAE) from system RAM to GPU VRAM. After this, the model occupies ~30–34 GB of the A40's 48 GB.

#### 4. Optional Optimizations (commented out)

```python
# pipe.transformer.set_attention_backend("flash")
# pipe.transformer.compile()
```

- **Flash Attention 2** — Replaces standard attention with a memory-efficient CUDA kernel. Faster and uses less VRAM. Requires `flash-attn` package and Ampere+ GPU.
- **`torch.compile()`** — Applies PyTorch 2.x graph compilation to the transformer. First inference is slow (compilation), but subsequent runs are ~20–40% faster. Good for batch generation, not worth it for one-off images.

#### 5. The Prompt

A detailed text prompt describing a photorealistic scene. The richness of the prompt directly affects output quality — Z-Image-Turbo's Qwen3 text encoder benefits from descriptive, specific language (camera model, lens, lighting conditions, etc.).

#### 6. Image Generation

```python
image = pipe(
    prompt=prompt,
    height=1024,
    width=1024,
    num_inference_steps=9,
    guidance_scale=0.0,
    generator=torch.Generator("cuda").manual_seed(42),
).images[0]
```

**What happens internally:**

1. **Tokenization** — The prompt is tokenized by the Qwen3 tokenizer into token IDs.
2. **Text Encoding** — Token IDs pass through the Qwen3 text encoder → produces text embeddings (conditioning for the diffusion model).
3. **Latent Initialization** — Random noise is generated in the VAE's latent space (shape: `[1, 16, 128, 128]` for 1024×1024).
4. **8-Step Diffusion** — The DiT transformer denoises the latent over 8 NFE steps. No classifier-free guidance (`guidance_scale=0.0`) — the model was trained to work without it.
5. **VAE Decoding** — The denoised latent is decoded by the VAE into a `[3, 1024, 1024]` pixel tensor.

#### 7. Saving the Output

```python
image.save("z_image_output1.png")
```

`pipe()` returns a `StableDiffusionPipelineOutput` with an `.images` list (one per batch item). `.images[0]` extracts the PIL Image, and `.save()` writes it as PNG.

---

### Understanding Latents

A **latent** is a compressed mathematical representation of an image — not the image itself, but an encoded version that the VAE can reconstruct into pixels.

#### Why Latents Exist

A 1024×1024 RGB image has **3,072,000 values** (3 channels × 1024 × 1024). Running diffusion directly on pixels would be enormously expensive. The VAE compresses the image into a much smaller space where diffusion is feasible.

#### The Latent Pipeline

```
Image [3, 1024, 1024]  →  VAE Encoder  →  Latent [16, 128, 128]
                                              ↓
                                      8-step diffusion (DiT)
                                              ↓
Latent [16, 128, 128]  →  VAE Decoder  →  Image [3, 1024, 1024]
```

- **Compression**: 3 × 1024 × 1024 = 3,072,000 values → 16 × 128 × 128 = 262,144 values (~12× compression)
- **Spatial factor**: 8× downscale per dimension (1024 → 128)
- **Channel expansion**: 3 RGB channels → 16 learned feature channels

#### What the 16 Channels Represent

The 16 channels don't correspond to visible colors like R, G, B. They're **abstract features** the VAE learned during training — edges, textures, color distributions, spatial structures — that *implicitly* encode the image. You can't look at a latent and see a picture, but the VAE decoder can reconstruct one from it.

#### Analogy

Think of it like an MP3: the original audio waveform is huge, but MP3 compresses it into a compact representation that still *sounds* the same when decoded. A latent is the "MP3 of an image" — compressed, not human-readable, but decodable into something that looks right.

#### Z-Image-Turbo Specifically

- **16 latent channels** (vs Stable Diffusion's 4) — more capacity for fine detail
- **8× spatial compression** — 1024px image → 128px latent grid
- Diffusion starts from **pure random noise** in latent space, and the DiT transformer refines it over 8 steps until it matches the prompt
- The VAE decoder then expands the result back to full pixels

---

### Understanding VAE

**VAE** stands for **Variational Autoencoder** — the component that bridges the gap between pixel space (where humans see images) and latent space (where diffusion happens).

#### What an Autoencoder Does

An autoencoder has two halves:

- **Encoder**: Compresses an image into a smaller representation (the latent)
- **Decoder**: Reconstructs the image from the latent

It's called "auto"-encoder because it trains against itself — the goal is for `decode(encode(image))` to look as close to the original image as possible.

#### What Makes It "Variational"

A regular autoencoder learns *any* compressed representation — the latent could be anything, with no structure. A **variational** autoencoder adds a constraint: the latent must follow a known probability distribution (a Gaussian/normal distribution). This means:

- The latent space is **smooth and continuous** — nearby points produce similar images
- You can **sample** from it (generate random noise that the decoder can turn into an image)
- This is essential for diffusion: the model adds noise to a latent, then learns to remove it, and the noise is drawn from this known distribution

#### The VAE in Z-Image-Turbo

Z-Image-Turbo uses an **AutoencoderKL** with **16 latent channels** and an **8× spatial compression** factor:

```
Encoder:  Image [3, 1024, 1024]  →  Latent [16, 128, 128]   (compress)
Decoder:  Latent [16, 128, 128]  →  Image [3, 1024, 1024]   (reconstruct)
```

- **16 channels** (vs Stable Diffusion's 4) — captures more detail: fine textures, color gradients, small structures
- **8× downscale** — each spatial dimension shrinks by 8 (1024 → 128), so the DiT transformer works on a 128×128 grid instead of 1024×1024
- The VAE weights are only **~160 MB** — tiny compared to the DiT (23 GB) and text encoder (7 GB)

#### Why Not Diffuse in Pixel Space?

A 1024×1024 image has 3 million values. Processing that through a transformer 8 times would require enormous compute and memory. By compressing to a 16×128×128 latent (262K values), the transformer does ~12× less work per step. The VAE absorbs the "heavy lifting" of pixel-level detail so the diffusion model can focus on high-level structure and semantics.

#### The Tradeoff

The VAE isn't perfect — it introduces a small quality loss. Some fine details may be slightly blurred or altered during encode→decode. This is why Z-Image-Turbo uses 16 channels instead of SD's 4: more channels means less information loss, at the cost of a slightly larger latent (but still far smaller than pixels).

#### Where the VAE Fits in the Pipeline

| Phase | Component | What it does |
|---|---|---|
| **Training only** | VAE Encoder | Compresses training images into latents for the DiT to learn from |
| **Inference: start** | Random noise | Pure Gaussian noise in latent space (no encoder needed) |
| **Inference: middle** | DiT Transformer | 8 denoising steps in latent space |
| **Inference: end** | VAE Decoder | Converts the final latent into a pixel image |

Note: during inference, only the **decoder** is used. The encoder is only needed during training to create the latent dataset. This is why the VAE is small — the decoder alone is even smaller.

---

### Understanding CUDA

**CUDA** (Compute Unified Device Architecture) is NVIDIA's platform for running general-purpose computations on GPUs. It's what makes a GPU do more than just render graphics — it lets you run AI models, scientific simulations, and parallel math on the GPU.

#### Why CUDA Matters Here

When the script says `pipe.to("cuda")`, it means: **"Move all model weights from system RAM to the NVIDIA GPU's VRAM, and run all computations on the GPU."**

Without CUDA, you'd run the model on a CPU — which would be **50–100× slower** for diffusion models. The A40 processes 8 denoising steps in seconds; a CPU would take minutes per step.

#### The CUDA Stack

```
Your Python code
      ↓
PyTorch (torch)            ← Python API
      ↓
CUDA Runtime               ← C/C++ library on the GPU
      ↓
NVIDIA GPU Driver          ← Kernel-level driver
      ↓
NVIDIA GPU Hardware        ← The actual chip (A40, A100, etc.)
```

- **PyTorch** provides the Python interface (`torch.cuda`, `.to("cuda")`, etc.)
- **CUDA** translates PyTorch operations into GPU instructions
- The **GPU** executes thousands of math operations in parallel

#### Key Concepts

**Parallelism:** A GPU has thousands of cores. CUDA splits work across them — e.g., computing all 262,144 latent values simultaneously rather than one at a time. This is why GPUs dominate AI workloads.

**VRAM (Video RAM):** The GPU's own memory, separate from system RAM. The A40 has 48 GB. When you call `.to("cuda")`, model weights are copied from system RAM → VRAM. All computation then happens using VRAM.

**`torch_dtype=torch.bfloat16`:** CUDA supports multiple numeric formats. bfloat16 uses 16 bits per weight instead of 32, letting you fit ~30 GB of model into VRAM instead of needing ~60 GB.

#### What Each Operation Uses

| Operation | Where it runs | Why |
|---|---|---|
| Model loading (`from_pretrained`) | CPU + system RAM | Downloads and deserializes weights |
| `pipe.to("cuda")` | Copies weights to GPU VRAM | So inference runs on GPU |
| Text encoding (Qwen3) | GPU via CUDA | Matrix multiplications on thousands of tokens |
| Diffusion (DiT transformer) | GPU via CUDA | 8 rounds of massive parallel computation |
| VAE decoding | GPU via CUDA | Upsamples latent → pixels |
| `image.save()` | CPU | Simple file I/O, no GPU needed |

#### Without CUDA

- `pipe.to("cuda")` → **error** if no NVIDIA GPU is present
- You *could* run on CPU with `pipe.to("cpu")`, but generation would take **minutes to hours** per image instead of seconds
- There's no real alternative for production inference — AMD has ROCm, Apple has Metal, but the ecosystem (diffusers, PyTorch, Flash Attention) is CUDA-first

---

*Plan created: 2026-06-20*
*Source: https://huggingface.co/Tongyi-MAI/Z-Image-Turbo*