# HuggingFace + RunPod Experiment: gemma4:31b

## Goal

Validate that gemma4:31b with 128K context meets quality bar for agentic AI coding consultancy, before committing to $4K+ hardware purchase.

## Estimated Cost

~$5-10 for a weekend experiment (A100 80GB at $1.39/hr on RunPod Secure Cloud)

## Path 1: Ollama on RunPod (fastest, 10 min setup)

### Step 1: Sign up

- Go to https://runpod.io
- Create account, add payment method

### Step 2: Create a pod

- **GPU**: A100 80GB (Secure Cloud, $1.39/hr)
- **Template**: Search "Ollama" in RunPod Hub — one-click template
- **Storage**: Add a Network Volume (~25GB) so model persists between restarts (~$2.50/month)
- Click **Deploy**

### Step 3: Pull the model

Open web terminal (or SSH):

```bash
ollama pull gemma4:31b
```

Wait ~2-3 min for 20GB download.

### Step 4: Connect from local machine

```bash
uhu --host http://YOUR_POD_IP:11434 --model gemma4:31b --ctx 202752
```

### Step 5: When done

Stop the pod. Billing stops. No contracts, no minimums.

---

## Path 2: HuggingFace + vLLM (learn the raw pipeline)

### Step 1: Create pod

- Same A100 80GB, but use a **blank PyTorch** template

### Step 2: Install dependencies

```bash
pip install vllm huggingface_hub
```

### Step 3: Download model from HuggingFace

**Option A: Full precision (FP16, ~60GB, best quality)**

```bash
huggingface-cli download google/gemma-4-31b-it --local-dir /model/gemma4-31b
```

Takes 10-15 min.

**Option B: Quantized GGUF (Q4_K_M, ~20GB, faster startup)**

```bash
huggingface-cli download bartowski/gemma-4-31b-it-GGUF \
  gemma-4-31b-it-Q4_K_M.gguf \
  --local-dir /model/gemma4-31b-gguf
```

### Step 4: Run inference server

**Option A: vLLM (FP16/safetensors) — OpenAI-compatible API**

```bash
vllm serve google/gemma-4-31b-it \
  --tensor-parallel-size 1 \
  --max-model-len 131072 \
  --gpu-memory-utilization 0.95
```

Starts server on port 8000.

**Option B: llama.cpp (GGUF quantized)**

```bash
# Install llama.cpp
git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp && make

./llama-server \
  -m /model/gemma4-31b-gguf/gemma-4-31b-it-Q4_K_M.gguf \
  -c 131072 \
  -ngl 99 \
  --port 8080
```

### Step 5: Connect uhu

```bash
# For vLLM:
uhu --host http://YOUR_POD_IP:8000/v1 --model google/gemma-4-31b-it

# For llama.cpp:
uhu --host http://YOUR_POD_IP:8080 --model gemma4-31b
```

---

## Comparison: Path 1 vs Path 2

|                     | Ollama on RunPod             | HuggingFace + vLLM               |
| ------------------- | ---------------------------- | -------------------------------- |
| Setup time          | 5 min                        | 30-60 min                        |
| Model format        | GGUF (quantized)             | FP16 (full precision)            |
| Quality             | Q4_K_M (slight quality loss) | Full precision (best quality)    |
| VRAM needed at 128K | ~35-40GB (fits A100)         | ~55-60GB (fits A100 80GB)        |
| Speed               | Fast (GGUF optimized)        | Slower startup, faster inference |
| Learning value      | Low (already know Ollama)    | High (full HF/vLLM stack)        |

---

## Key Notes

- **RunPod billing**: Per-second, only while pod is running. Stop pod = stop paying.
- **Cold start overhead**: ~5 min to pull model on fresh start. Network Volume eliminates this ($2.50/month).
- **Spot vs Secure Cloud**: Use Secure Cloud ($1.39/hr). Spot is cheaper but can be killed anytime.
- **gemma4:31b specs**: 20GB (Q4_K_M), 31B params dense, 256K context window.
- **Memory at 128K context**: ~35-40GB (Q4 on A100 fits comfortably; ~55-60GB for FP16).

---

## Decision Framework After Experiment

If gemma4:31b at 128K context is good enough for coding work:

- **Occasional use**: Continue RunPod, ~$85/month at 2hr/day
- **Daily/consultancy use**: Buy MacBook M5 Pro 64GB (~$4,450), pays for itself in ~4 years vs RunPod
- **Privacy-sensitive clients**: MacBook is the only option — data never leaves the machine
