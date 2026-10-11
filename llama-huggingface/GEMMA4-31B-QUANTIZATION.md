# Gemma 4 31B — Available Quantizations

> Last updated: July 2026

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

### Key Differences

- **Multimodal:** All 31B models accept images + text as input (vision-language models)
- **`-it` (instruction-tuned):** Optimized for conversational/chat use — by far the most popular variant (27.8M downloads)
- **`-assistant` variant:** Uses `gemma4_assistant` architecture, supports any-to-any generation (text + image output), created April 2026
- **QAT (Quantization-Aware Training):** Models trained with quantization simulation, retaining better accuracy after quantization compared to post-training quantization methods

## Architecture Details

- **Base architecture (31B/31B-it):** `gemma4` — `Gemma4ForConditionalGeneration`
- **Assistant variant:** `gemma4_assistant` — any-to-any (can generate both text and images)
- **Model class:** `AutoModelForMultimodalLM` (safetensors variants), `AutoModel` (GGUF)
- **Tokenizer:** Special tokens `<bos>`, `<eos>`, `<mask>`, `<pad>`, `<unk>` with Jinja chat templates

## Notation Guide: ℝⁿ

Throughout this document, **ℝⁿ** (read: "R-n" or "real n-space") denotes the set of all vectors with **n** real-number components.

- **ℝ** = the set of all real numbers (…, -1.5, 0, 3.14, …)
- **ℝ³** = all possible 3D vectors: `[x, y, z]` where x, y, z are real numbers
- **ℝ⁵³⁷⁶** = all possible vectors with 5,376 real-number components

When we say a token is "a vector in ℝ⁵³⁷⁶", it means each token is represented by a list of 5,376 real numbers. A weight matrix that maps ℝ⁵³⁷⁶ → ℝ⁸¹⁹² takes a 5,376-number vector as input and produces an 8,192-number vector as output — it's a function between two vector spaces.

| Notation | Meaning | In this model |
|----------|---------|---------------|
| ℝ⁵³⁷⁶ | Vectors with 5,376 components | Token hidden states |
| ℝ⁸¹⁹² | Vectors with 8,192 components | Query (Q) output space |
| ℝ²¹⁵⁰⁴ | Vectors with 21,504 components | FFN intermediate space |
| ℝ²⁶²¹⁴⁴ | Vectors with 262,144 components | Vocabulary (token ID) space |

The superscript is the **dimension of the vector space** — how many numbers each vector contains. This is the math meaning of "dimension" (size of the space), not the tensor rank (number of axes).

### Origin of the ℝⁿ Notation

| Period | Development |
|--------|-------------|
| 1637 | Descartes invents Cartesian coordinates — the idea of ℝ² as a plane |
| 1888 | Peano formally defines vector spaces and ℝⁿ |
| 1930s–50s | Bourbaki group (French mathematicians) standardizes ℝⁿ notation in their textbooks |
| 1960s | Blackboard bold ℝ (double-struck) appears on university chalkboards to distinguish the set ℝ from the variable R |
| 1990s | LaTeX adopts `\mathbb{R}` for the symbol |

- **ℝ** = the set of real numbers, from the German **"Reell"** (real). The double-struck style distinguishes it from a variable named R.
- **The superscript ⁿ** = Cartesian product. ℝ² = ℝ × ℝ (all pairs), ℝ³ = ℝ × ℝ × ℝ (all triples), ℝⁿ = ℝ × ℝ × ... × ℝ (n times).

---

## How Transformers Work

**Transformers** are the engine behind modern AI language models (like GPT, Claude, Gemma, etc.). Here's the core idea:

### The Problem
When reading a sentence, the meaning of a word depends on **context** — other words around it. Older models processed words one at a time, so they "forgot" early words by the time they reached the end.

### The Solution: Attention
Transformers use a mechanism called **self-attention**:

- For every word, the model looks at **all other words** in the sentence simultaneously
- It calculates how much each word should "pay attention" to every other word
- This creates a weighted mix of context for each word

Example: In *"The bank of the river"*, attention helps the model know "bank" relates to "river", not finance.

### How It Works (Simplified)

1. **Input** → Text is broken into tokens (words/subwords) and converted to numbers (embeddings) — each token becomes a vector in ℝ⁵³⁷⁶
2. **Attention** → Each token asks: *"Which other tokens are relevant to me?"* and gathers information from them — this is the Q/K/V projection
3. **Feed-Forward** → Each token is processed through a neural network (FFN) — projected into ℝ²¹⁵⁰⁴ then back to ℝ⁵³⁷⁶
4. **Repeat** → Steps 2-3 repeat 60 times (called "layers"), building deeper understanding
5. **Output** → The final representations predict the next token

### Key Concepts

| Concept | Simple Meaning | In Gemma 4 31B |
|---------|---------------|----------------|
| **Self-attention** | Every word looks at every other word to gather context | Q/K/V projections transform tokens, then attention scores determine relevance |
| **Multi-head** | Do attention multiple times in parallel — each "head" focuses on different relationships | 32 query heads (sliding) or 32/4 heads (full), each operating in ℝ²⁵⁶ or ℝ⁵¹² |
| **Grouped Query Attention** | Multiple Q heads share the same K/V heads, reducing memory | 32 Q heads share 16 KV heads (sliding) or 4 KV heads (full) |
| **Sliding attention** | Each token only attends to nearby tokens (window of 1,024) | 50 of 60 layers — cheaper, captures local patterns (syntax, nearby words) |
| **Full attention** | Each token attends to all other tokens in the entire sequence | 10 of 60 layers — expensive, captures long-range dependencies (variable references across pages) |
| **Positional encoding** | Add "position tags" so the model knows word order | Proportional RoPE (p-RoPE) for full attention, standard RoPE for sliding |
| **Layers** | Stack many attention+processing blocks for deeper understanding | 60 layers, each ~479M–534M parameters |
| **FFN** | Per-token neural network that "processes" the gathered context | Projects ℝ⁵³⁷⁶ → ℝ²¹⁵⁰⁴ → ℝ⁵³⁷⁶ (4× expansion with gate) |

### Why It's Powerful
- **Parallelizable**: Unlike older sequential models, all tokens are processed at once → much faster training
- **Long-range context**: Word 1 can directly attend to word 1000 — no information bottleneck
- **Scalable**: Just add more layers, heads, and data → bigger model = better performance

### One-Liner
> A transformer is a model that lets every word "talk to" every other word to figure out meaning, then repeats this process many times to build deep understanding before predicting what comes next.

### Gemma 4 31B's Hybrid Attention

Gemma 4 31B uses a **hybrid attention** architecture — it interleaves two types of attention across its 60 layers:

| | Sliding Attention | Full Attention |
|---|---|---|
| **How many tokens seen** | Last 1,024 tokens only | All tokens in the sequence |
| **Cost** | O(n × window) | O(n²) |
| **Good for** | Syntax, local context, nearby word relationships | Long-range reasoning, variable tracking across files |
| **Layers** | 50 of 60 (layers 0-4, 6-10, 12-16, ...) | 10 of 60 (layers 5, 11, 17, 23, 29, 35, 41, 47, 53, 59) |
| **KV heads** | 16 | 4 (unified K/V) |
| **Head dimension** | 256 | 512 |
| **RoPE type** | Standard | Proportional (p-RoPE) |

By using sliding attention for 83% of layers and full attention only every 6th layer, Gemma 4 gets long-range understanding at a fraction of the compute cost. Information from distant tokens still flows through the full-attention layers like relay stations.

---

## Model Dimensions

| Dimension | Value | What It Means | Math Description |
|-----------|-------|--------------|-----------------|
| Hidden size (d_model) | 5,376 | The "width" of the model — how many numbers represent each token at every layer. Bigger = more expressive but more expensive. | Each token is a vector in ℝ⁵³⁷⁶ |
| FFN intermediate size | 21,504 (4× expansion) | How wide the feed-forward network expands before compressing back. 4× is standard — the model "thinks harder" in a wider space then compresses. | FFN projects tokens into ℝ²¹⁵⁰⁴ then back to ℝ⁵³⁷⁶ |
| Attention heads (Q) | 32 | How many parallel attention patterns each layer computes. Each head can focus on different relationships (grammar, meaning, position). | Hidden vector split into 32 parallel subspaces |
| KV heads (sliding) | 16 | How many key/value representations are shared across query heads. Fewer KV heads = less memory, slightly less precision. | 16 key/value subspaces (Grouped Query Attention) |
| KV heads (full/global) | 4 | Fewer KV heads for global attention to save memory on long contexts. K and V are unified (no separate V tensor). | 4 global key/value subspaces (unified K/V) |
| Head dimension (sliding) | 256 | Size of each attention head's subspace. Determines how much detail each head can capture. | Each attention head operates in ℝ²⁵⁶ |
| Head dimension (full/global) | 512 | Global heads are wider (2×) to compensate for having fewer of them. They need more capacity per head for long-range reasoning. | Each global head operates in ℝ⁵¹² |
| Layers | 60 (50 sliding + 10 full) | How many times the attention+FFN transformation is applied. More layers = deeper understanding, but slower and more expensive. | 60 sequential rank-2 tensor transformations |
| Vocabulary size | 262,144 | How many distinct tokens the model knows. Covers text, code, and special tokens. Larger vocab = better for multilingual and code. | Embedding maps 262K token IDs → vectors in ℝ⁵³⁷⁶ |
| Context length | 262,144 (256K) | Maximum number of tokens the model can process at once. Determines how much text/code you can feed in a single prompt. | Maximum sequence length (axis size of the time dimension) |
| Sliding window | 1,024 | How many recent tokens each sliding attention layer can see. Local context for syntax and nearby word relationships. | Local attention sees 1,024 tokens back (local ℝ¹⁰²⁴ window) |

### Per-Layer Parameter Counts

| Component | What It Does | Sliding Attention Layer | Full Attention Layer | Math Description |
|-----------|-------------|------------------------|---------------------|-----------------|
| Q projection | "What am I looking for?" — transforms each token into a query vector for attention | 5,376 × 8,192 = 44.0M | 5,376 × 16,384 = 88.1M | Rank-2 tensor, linear map ℝ⁵³⁷⁶ → ℝ⁸¹⁹² (or ℝ¹⁶³⁸⁴) |
| K projection | "What do I contain?" — transforms each token into a key vector for matching | 5,376 × 4,096 = 22.0M | 5,376 × 2,048 = 11.0M | Rank-2 tensor, linear map ℝ⁵³⁷⁶ → ℝ⁴⁰⁹⁶ (or ℝ²⁰⁴⁸) |
| V projection | "What info do I offer?" — transforms each token into a value vector to share | 5,376 × 4,096 = 22.0M | *(unified with K)* | Rank-2 tensor, linear map ℝ⁵³⁷⁶ → ℝ⁴⁰⁹⁶ |
| O projection | Combines all attention head outputs back into the hidden size | 8,192 × 5,376 = 44.0M | 16,384 × 5,376 = 88.1M | Rank-2 tensor, linear map ℝ⁸¹⁹² → ℝ⁵³⁷⁶ (or ℝ¹⁶³⁸⁴ → ℝ⁵³⁷⁶) |
| FFN up | Expands token from hidden size into wider space for "thinking" | 5,376 × 21,504 = 115.6M | 5,376 × 21,504 = 115.6M | Rank-2 tensor, linear map ℝ⁵³⁷⁶ → ℝ²¹⁵⁰⁴ |
| FFN gate | Controls which expanded features to pass through (like a filter/switch) | 5,376 × 21,504 = 115.6M | 5,376 × 21,504 = 115.6M | Rank-2 tensor, linear map ℝ⁵³⁷⁶ → ℝ²¹⁵⁰⁴ |
| FFN down | Compresses the expanded representation back to hidden size | 21,504 × 5,376 = 115.6M | 21,504 × 5,376 = 115.6M | Rank-2 tensor, linear map ℝ²¹⁵⁰⁴ → ℝ⁵³⁷⁶ |
| Norms + scales | Stabilizes values and scales outputs between layers | ~0.02M | ~0.02M | Rank-1 tensors (vectors in ℝ⁵³⁷⁶) and rank-0 (scalars) |
| **Per-layer total** | | **~479M** | **~534M** | |

### Total Parameter Count

| Component | What It Does | Calculation | Parameters | Math Description |
|-----------|-------------|-------------|-----------|-----------------|
| Embedding (tied with output) | Translates between token IDs and vectors — the front door and back door of the model | 262,144 × 5,376 | 1.41B | Rank-2 tensor, lookup table mapping token IDs → vectors in ℝ⁵³⁷⁶ |
| 50 sliding attention layers | Local context processing — syntax, nearby word relationships | 50 × 479M | 23.95B | 50 sequential rank-2 transformations per component |
| 10 full attention layers | Long-range context processing — variable tracking, cross-file reasoning | 10 × 534M | 5.34B | 10 sequential rank-2 transformations per component |
| **Text model total** | | | **~30.7B** | ~30.7B individual scalars (rank-0 tensors) |
| Vision encoder (mmproj) | Converts image features into the same ℝ⁵³⁷⁶ space as text tokens | | ~0.55B | Projects vision features into ℝ⁵³⁷⁶ |
| **Total with vision** | | | **~31.25B** | |

### Tensor Rank Summary

All learnable parameters in this model are rank ≤ 2:

| Rank | Shape | What it represents | Example |
|------|-------|--------------------|---------|
| 0 (scalar) | `[1]` | Single scale value | `layer_output_scale.weight` |
| 1 (vector) | `[5376]` | Per-channel scale/normalization | `attn_norm.weight`, `ffn_norm.weight` |
| 2 (matrix) | `[5376, 8192]` | Linear transformation between vector spaces | `attn_q.weight`, `ffn_up.weight` |

**No rank-3 or higher tensors exist in this model.** The largest matrix is the embedding at `[262,144 × 5,376]` containing 1.41B individual scalars. The maximum axis size (ML "dimension") is 262,144 (vocabulary size).

> **Note:** Full attention layers use unified K/V projections (no separate V tensor) and 512-dim heads with 4 global KV heads, making Q and O projections 2× larger than sliding layers. This is why full attention layers have ~55M more parameters each.

---

## ML vs. Math Terminology

The ML terminology is confusing because it uses "dimension" in a way that doesn't directly map to the math you learned.

### The Math You Know

| Rank | Name | Example | How many indices to address one element |
|------|------|---------|----------------------------------------|
| 0 | Scalar | `5` | None — it's just a number |
| 1 | Vector | `[1, 3, 7]` | One: `v[2] = 7` |
| 2 | Matrix | `[[1,2],[3,4]]` | Two: `m[1][0] = 3` |
| 3+ | Tensor | 3D grid of numbers | Three+: `t[2][1][0]` |

This is **tensor rank** (or order) — how many axes a data structure has.

### What ML Calls "Dimensions"

When ML people say "hidden dimension = 5,376", they're **not** talking about rank. They're talking about the **size along one axis** of a rank-1 or rank-2 tensor.

In math terms:

| ML term | What it actually is | Math description |
|---------|-------------------|-----------------|
| "Hidden dimension" = 5,376 | Size of a vector | A vector in **ℝ⁵³⁷⁶** — a 1D tensor with 5,376 components |
| "Q projection" = 5,376 × 8,192 | A matrix | A rank-2 tensor, a linear map **ℝ⁵³⁷⁶ → ℝ⁸¹⁹²** |
| "Embedding" = 262,144 × 5,376 | A matrix | A rank-2 tensor, a lookup table mapping token IDs to vectors in **ℝ⁵³⁷⁶** |

### The Key Confusion

In math, a vector `[1, 3, 7]` is **1-dimensional** (rank 1) but lives in **ℝ³** (a 3-dimensional space). These are two different uses of "dimension":

- **Rank** = how many axes the tensor has (math dimension)
- **Size** = how many elements along one axis (ML "dimension")

ML people say "dimension" when they mean "size along an axis." A weight matrix of shape `[5376, 8192]` is:

- **Rank 2** in math (it's a matrix)
- Has **dimensions** 5,376 and 8,192 in ML speak (sizes of its two axes)
- Contains **5,376 × 8,192 = 44M parameters** (individual scalars)

### The Full Mapping

| Math concept | Math term | ML term | Gemma 4 31B example |
|-------------|-----------|---------|---------------------|
| Single number | Scalar (rank 0) | Parameter / weight | `0.137` |
| Ordered list of numbers | Vector (rank 1) | "Dimension" = axis size | Token embedding: 5,376 numbers per token |
| Grid of numbers | Matrix (rank 2) | Weight matrix | Q projection: 5,376 × 8,192 numbers |
| 3D+ grid of numbers | Tensor (rank 3+) | Weight tensor | Not used in this model |

| ML phrase | What it actually means | Math description |
|-----------|----------------------|-----------------|
| "Hidden dimension = 5,376" | Size of the token vector | A vector in ℝ⁵³⁷⁶ |
| "Q projection = 5,376 × 8,192" | A weight matrix | A linear map ℝ⁵³⁷⁶ → ℝ⁸¹⁹² |
| "Embedding = 262,144 × 5,376" | A lookup table | Maps token IDs to vectors in ℝ⁵³⁷⁶ |
| "Parameters = 44M" | Number of scalars in a weight matrix | 5,376 × 8,192 = 44,032,512 individual numbers |

### Why It Matters

- **Same dimensions → same parameter count** (architecture is fixed)
- **Same parameter count → different file sizes** depending on quantization:
  - FP16: 44M params × 2 bytes = 88 MB
  - Q8: 44M params × 1 byte = 44 MB
  - Q4: 44M params × 0.5 bytes = 22 MB

The dimensions don't change with quantization — only the **precision of each parameter** changes. That's why Q8_0 and UD-Q8_K_XL have the same architecture (same dimensions, same parameter count of ~30.7B) but different file sizes (30.4 GB vs 32.6 GB) — some parameters are stored at higher precision.

---

## Overview

Gemma 4 31B is a 31-billion parameter multimodal (image-text-to-text) model from Google. Multiple quantized versions are available on HuggingFace from both **Google** (official) and **Unsloth** (community). This document catalogs all available quantization variants, their file sizes, and trade-offs.

---

## Google Official Quantizations

Google provides a limited set of official quantized variants:

| Repo | Format | Quantization | Model Size | Notes |
|------|--------|-------------|-----------|-------|
| `google/gemma-4-31B-it-qat-q4_0-gguf` | GGUF | Q4_0 (QAT) | ~17.65 GB | Includes mmproj (~1.2 GB) |
| `google/gemma-4-31B-it-qat-w4a16-ct` | safetensors | W4A16 (compressed-tensors) | ~21.67 GB | 4-bit weights, 16-bit activations |
| `google/gemma-4-31B-it-qat-q4_0-unquantized` | safetensors | Unquantized (FP16/BF16) | ~65 GB (est.) | Full-precision QAT-trained weights |
| `google/gemma-4-31B-it-qat-q4_0-unquantized-assistant` | safetensors | Unquantized (FP16/BF16) | ~67 GB (est.) | Assistant-tuned variant |

**Key points:**
- Google only provides **one quantization level** (Q4_0) for the 31B model in GGUF format.
- The `w4a16-ct` variant uses the `compressed-tensors` format, suitable for vLLM / transformers.
- The `unquantized` variants contain full-precision weights that were QAT-trained (optimized for subsequent Q4_0 quantization).
- QAT (Quantization-Aware Training) means the model was trained with quantization in mind, so Q4_0 QAT typically preserves more quality than standard post-training Q4_0.

---

## Unsloth Community Quantizations

Repo: **`unsloth/gemma-4-31B-it-GGUF`**

Unsloth provides the widest range of quantization options, including both standard K-quants and their proprietary Unsloth Dynamic (UD) variants.

### Standard K-Quants

| Quantization | Size (GB) | Notes |
|---|---|---|
| Q3_K_S | 12.30 | Smallest standard |
| Q3_K_M | 13.72 | |
| Q4_0 | 16.15 | Same as Google's Q4_0 |
| Q4_K_S | 16.21 | |
| IQ4_NL | 16.10 | Importance-matrix 4-bit, non-linear |
| IQ4_XS | 15.25 | Importance-matrix 4-bit, extra small |
| Q4_1 | 17.81 | 4-bit with per-block scale |
| Q4_K_M | 17.07 | Popular quality/size balance |
| Q5_K_S | 19.68 | |
| Q5_K_M | 20.17 | |
| Q6_K | 23.47 | Near-lossless |
| Q8_0 | 30.39 | Essentially lossless |

### Unsloth Dynamic (UD) — Imatrix-optimized

| Quantization | Size (GB) | Notes |
|---|---|---|
| UD-IQ2_XXS | 7.95 | Smallest overall |
| UD-IQ2_M | 10.01 | |
| UD-IQ3_XXS | 11.02 | |
| UD-Q2_K_XL | 10.97 | |
| UD-Q3_K_XL | 14.31 | |
| UD-Q4_K_XL | 17.53 | Best quality/size trade-off |
| UD-Q5_K_XL | 20.39 | |
| UD-Q6_K_XL | 25.63 | |
| UD-Q8_K_XL | 32.60 | Highest quality |

### Additional Files

| File | Size | Purpose |
|---|---|---|
| mmproj-BF16.gguf | 1.12 GB | Multimodal projector (BF16) |
| mmproj-F16.gguf | 1.12 GB | Multimodal projector (F16) |
| mmproj-F32.gguf | 2.15 GB | Multimodal projector (F32) |
| mtp-gemma-4-31B-it.gguf | 0.48 GB | Multi-token prediction (speculative decoding) |
| imatrix_unsloth.gguf | 13 MB | Importance matrix calibration data |

---

## Unsloth QAT Quantization

Repo: **`unsloth/gemma-4-31B-it-qat-GGUF`**

A single QAT-optimized variant:

| Quantization | Size (GB) | Notes |
|---|---|---|
| UD-Q4_K_XL (QAT) | ~17.29 | QAT-trained, best Q4 quality |

Includes mmproj (BF16/F16/F32) and MTP draft model (~280 MB).

---

## Standard K-Quants vs. Unsloth Dynamic (UD)

### Standard K-Quants
These are the **original llama.cpp quantization schemes**. They use a fixed quantization strategy per tensor:

- **Q3_K** — 3-bit quantization with varying block sizes (S/M for different k-bit subsets)
- **Q4_0/Q4_1** — 4-bit with 32-element blocks; Q4_1 adds a per-block scale
- **Q4_K_S/Q4_K_M** — 4-bit K-quant with mixed precision (some layers get more bits than others)
- **Q5_K_S/Q5_K_M** — 5-bit, same mixed-precision approach
- **Q6_K** — 6-bit, near-lossless
- **Q8_0** — 8-bit, essentially lossless
- **IQ4_NL/IQ4_XS** — Importance-matrix 4-bit variants with simpler calibration

**Key trait:** Every layer gets the same quantization treatment (within the S/M variant). The bit budget is spread uniformly.

### Unsloth Dynamic (UD) — Imatrix-optimized
These combine two techniques:

1. **Importance Matrix (imatrix)** — Before quantizing, calibration data is run through the model to measure which layers and tensors matter most for output quality. The `imatrix_unsloth.gguf` file stores these importance scores.

2. **Dynamic bit allocation** — Instead of applying the same quantization to every layer, UD variants allocate more bits to important tensors and fewer bits to less important ones. For example, attention layers that heavily influence output might get Q5_K precision while less-critical MLP layers get Q3_K — all within the same model file.

### Comparison

| Aspect | Standard K-Quants | Unsloth Dynamic (UD) |
|--------|------------------|----------------------|
| **Bit allocation** | Uniform across layers | Weighted by importance |
| **Quality at same size** | Baseline | Typically better — important layers retain more precision |
| **Size at same quality** | Larger for equivalent quality | Smaller — bits are spent where they matter |
| **Calibration** | None or basic | Uses imatrix from real calibration data |
| **Naming** | Q4_K_M, Q5_K_S, etc. | UD-Q4_K_XL, UD-IQ2_M, etc. |
| **"XL" suffix** | N/A | Extra precision on critical tensors vs. the non-XL version |

**Bottom line:** UD variants give you better quality per GB than standard K-quants at the same approximate size. If choosing between a standard and UD variant of similar size, go with UD.

### Deep Dive: Why UD-Q8_K_XL Is Larger Than Q8_0

It seems counterintuitive that a "dynamic" quantization could be **larger** than a uniform 8-bit one. Here's why:

**Q8_0** gives every tensor exactly 8 bits. That's the ceiling — no layer gets more than 8 bits.

**UD-Q8_K_XL** doesn't redistribute the same bit budget. Instead, it **adds more bits to important tensors** — pushing some layers **above 8-bit** precision (e.g., into K-quant mixed-precision formats that use higher bit-widths for critical tensors). The "XL" suffix means extra precision on top of the base UD allocation.

The size increase comes from:

1. **Important layers get >8 bits** — Critical attention heads and output layers are quantized at higher precision (e.g., 12-bit or 16-bit K-quant blocks) because the imatrix identified them as disproportionately impacting output quality.
2. **Less important layers still get ~8 bits or slightly less** — But the savings there don't offset the extra bits on critical layers, because the important tensors tend to be larger.
3. **Net result: total bits > 8 bits × parameters** — The model is larger overall because the bit budget isn't fixed — it's expanded for quality-critical tensors.

#### Coding Task Analogy

Imagine you're a **senior developer** reviewing a codebase with limited "attention budget" (VRAM), deciding how much precision to devote to understanding each part.

**Q8_0 — Uniform Code Review**

You give **every file the same level of attention** — 8 minutes per file, whether it's:

- `main.py` — the core entry point (critical)
- `utils.py` — helper functions (important)
- `__init__.py` — just imports (trivial)
- `legacy_compat.py` — rarely called (unimportant)

Result: Trivial files get more scrutiny than they need; critical files don't get **extra** attention beyond the standard 8 minutes.

**UD-Q8_K_XL — Importance-Weighted Code Review**

Before reviewing, you run **profiling** (imatrix calibration) and discover:

| File | Q8_0 (min) | UD-Q8_K_XL (min) | Size (lines) |
|------|-----------|-------------------|-------------|
| `main.py` | 8 | **14** | 2,000 lines |
| `utils.py` | 8 | **10** | 800 lines |
| `__init__.py` | 8 | **3** | 50 lines |
| `legacy_compat.py` | 8 | **4** | 100 lines |

**Q8_0 total attention**: 8 × (2000 + 800 + 50 + 100) = 23,600 unit-minutes
**UD-Q8_K_XL total attention**: 14×2000 + 10×800 + 3×50 + 4×100 = **36,950 unit-minutes**

The extra time on the **large, critical files** (`main.py` getting 14 min instead of 8) far outweighs the savings on the **small, trivial files** (`__init__.py` dropping from 8 to 3). The net result is **more total attention** — which translates to a larger file size.

#### Why This Matters for Coding Tasks

When you ask the model to **write code**, it relies heavily on:

- **Attention layers** — understanding context, variable relationships, function call chains
- **Output projection layers** — generating syntactically correct tokens

These are exactly the layers that UD-Q8_K_XL **boosts above 8-bit**. So for coding:

- **Q8_0**: Every layer is 8-bit. Good enough for most tasks, essentially lossless.
- **UD-Q8_K_XL**: The layers that **matter most for code generation** get >8-bit precision. The difference may show up in:
  - Complex multi-step reasoning (nested logic, recursive algorithms)
  - Consistent variable naming across long contexts
  - Correct syntax in less common languages or frameworks

**Practical advice**: At 8-bit, both are near-lossless. The quality difference is negligible for most use cases. **Q8_0 is the better default** — it's smaller and the quality is already indistinguishable from full precision. Only choose UD-Q8_K_XL if you're chasing every last drop of quality and don't mind the extra ~2 GB.

### Inspection Results: UD-Q8_K_XL Per-Tensor Breakdown

Actual inspection of the GGUF file reveals that UD-Q8_K_XL uses **only two quantization types** — no intermediate K-quants:

| Type | Tensors | Size (GB) | % of Model |
|------|---------|-----------|------------|
| Q8_0 | 381 | 27.86 | 85.5% |
| F16 | 30 | 4.74 | 14.5% |
| F32 | 422 | 0.005 | ~0% (norms only) |

The F16 boost targets **6 out of 60 layers** — the "bookends" of the transformer:

| Layer | Type | Q | K | V | O | FFN_up | FFN_gate | FFN_down |
|-------|------|---|---|---|---|--------|----------|----------|
| 1 | sliding | **F16** | **F16** | Q8_0 | Q8_0 | **F16** | **F16** | **F16** |
| 52 | sliding | **F16** | **F16** | Q8_0 | Q8_0 | **F16** | **F16** | **F16** |
| 53 | full | **F16** | **F16** | — | Q8_0 | **F16** | **F16** | **F16** |
| 57 | sliding | **F16** | **F16** | Q8_0 | Q8_0 | **F16** | **F16** | **F16** |
| 58 | sliding | **F16** | **F16** | Q8_0 | Q8_0 | **F16** | **F16** | **F16** |
| 59 | full | **F16** | **F16** | — | Q8_0 | **F16** | **F16** | **F16** |
| All others | mixed | Q8_0 | Q8_0 | Q8_0 | Q8_0 | Q8_0 | Q8_0 | Q8_0 |

**Key observations:**
- Layer 1 (early) and layers 52-59 (final 8) get F16 — initial feature extraction and output refinement
- V and O projections stay Q8_0 even in F16 layers — the imatrix found attention *scoring* (Q, K) and *knowledge transformation* (FFN) benefit more from 16-bit than attention *value aggregation* (V) and *output mixing* (O)
- The ~2 GB size premium comes entirely from these 30 F16 tensors (4.74 GB vs. ~2.37 GB if they were Q8_0)

**For coding tasks:** UD-Q8_K_XL is the better choice — F16 on Q/K attention scoring improves variable tracking across long contexts, and F16 on final-layer FFN improves syntax generation and reduces API hallucinations. But since 85.5% of the model is identical Q8_0, the practical difference is marginal. If the extra ~2 GB costs you context length or VRAM, Q8_0 is the smarter choice.

---

## VRAM Recommendations

| VRAM | Recommended Quantization | Notes |
|------|--------------------------|-------|
| 8 GB | UD-IQ2_XXS (7.95 GB) + mmproj-F16 | Tight fit, quality loss |
| 12 GB | Q3_K_S (12.3 GB) | Borderline; consider offloading |
| 16 GB | UD-Q4_K_XL (17.5 GB) + mmproj | Best quality/size trade-off |
| 24 GB | Q5_K_M (20.2 GB) or UD-Q5_K_XL (20.4 GB) + mmproj | Great quality |
| 32+ GB | Q6_K (23.5 GB) or Q8_0 (30.4 GB) | Near-original quality |

> **Note:** Add ~1.1 GB (mmproj-F16) to model size for total VRAM needed with vision support. Add ~0.5 GB for MTP speculative decoding if used. Context length (up to 262K tokens) also consumes additional VRAM at runtime.

---

## Ollama Availability

The official Ollama library (`ollama.com/library/gemma4`) provides limited 31B quantization options:

| Ollama Tag | Quantization | Size | Notes |
|---|---|---|---|
| `gemma4:31b` | Q4_K_M (default) | ~20 GB | Default pull — includes mmproj |
| `gemma4:31b-it-q4_K_M` | Q4_K_M (explicit) | ~20 GB | Same as default, explicit tag |

**To run:** `ollama run gemma4:31b`

### Using Other Quantizations on Ollama

For quantizations not in the official library (Q3, Q5, Q6, Q8, UD variants), pull directly from HuggingFace:

```bash
# Unsloth standard GGUF
ollama run hf.co/unsloth/gemma-4-31B-it-GGUF:Q5_K_M

# Unsloth Dynamic (UD)
ollama run hf.co/unsloth/gemma-4-31B-it-GGUF:UD-Q4_K_XL

# Unsloth QAT
ollama run hf.co/unsloth/gemma-4-31B-it-qat-GGUF:UD-Q4_K_XL
```

> **Note:** When pulling from HuggingFace, the tag after the colon must match the exact filename suffix (e.g., `Q5_K_M`, `UD-Q3_K_XL`, `IQ4_XS`).

---

## Ollama & HuggingFace — Format Compatibility

Ollama **cannot** run every model on HuggingFace directly. Only **GGUF-format** models are supported.

### What works directly

Any GGUF model on HuggingFace can be pulled and run with:

```bash
ollama run hf.co/{username}/{repo}:{quantization}
```

Example: `ollama run hf.co/unsloth/gemma-4-31B-it-GGUF:Q5_K_M`

There are ~45K GGUF models on HuggingFace that work this way.

### What doesn't work directly

| Format | Direct Ollama support? | Workaround |
|--------|----------------------|------------|
| **GGUF** | ✅ Yes | — |
| **Safetensors** | ❌ No | Convert to GGUF first |
| **PyTorch `.bin`** | ❌ No | Convert to GGUF first |

Most models on HuggingFace are in **safetensors** format (the native HuggingFace format), which Ollama cannot import directly.

### Converting non-GGUF models for Ollama

1. **Download** the model from HuggingFace (safetensors / PyTorch)
2. **Convert** to GGUF using `llama.cpp` conversion scripts (e.g., `convert_hf_to_gguf.py`)
3. **Quantize** (optional) to reduce size
4. **Create a Modelfile** pointing to the GGUF file and run:
   ```bash
   ollama create mymodel -f Modelfile
   ollama run mymodel
   ```

> **Tip:** For fine-tuned adapters in safetensors format, you can create a Modelfile with a `FROM` command pointing to the base GGUF model and an `ADAPTER` command pointing to the adapter weights. See [Ollama Import Docs](https://docs.ollama.com/import).

---

## How This Model Works — End-to-End Inference

This section walks through what happens when you send a prompt to Gemma 4 31B, from text to prediction, using the math language introduced earlier.

### Step 1: Tokenization — Text → Numbers

Your input text is chopped into **tokens** (words or subwords) and each token gets an integer ID from the vocabulary.

```
"Write a Python function" → [4288, 452, 14952, 3450]  (4 token IDs)
```

The vocabulary has 262,144 possible tokens. Each ID is just a number — an index into the embedding table.

> **Math reference:** A list of integers — a rank-1 tensor (vector) in ℤ⁴ (4 integer components). Each component is a scalar (rank-0 tensor) indexing into the vocabulary space ℝ²⁶²¹⁴⁴.

### Step 2: Embedding — Numbers → Vectors

Each token ID is looked up in the **embedding matrix** (a rank-2 tensor of shape `[262,144 × 5,376]`). This converts the integer into a vector in ℝ⁵³⁷⁶ — a list of 5,376 real numbers that captures the token's meaning.

```
Token ID 4288 → vector [0.023, -0.137, 0.541, ...]  (5,376 numbers)
Token ID 452  → vector [-0.089, 0.214, -0.033, ...]  (5,376 numbers)
```
At this point, each token is a point in ℝ⁵³⁷⁶ — a 5,376-dimensional space where similar words are close together.

Every number in this matrix is a learned weight (a parameter). The count is simply rows × columns: 262,144 (vocabulary size) × 5,376 (hidden size) = **1.41 billion parameters**. This same pattern (shape `[A × B]` = A × B parameters) applies to every weight matrix in the model, and the total of ~31B parameters is just the sum:

```
1.41B  (embedding)
+ 50   (layer count) × 479M (per-layer) = 23.95B  (sliding layers)
+ 10   (layer count) × 534M (per-layer) = 5.34B   (full layers)
+ 0.55B  (vision)
≈ 31B  (total params)
```

(See [How the Math Scales to 31B](#how-the-math-scales-to-31b) for the full breakdown.)

> **Math reference:**
> **Math reference:** The embedding is a rank-2 tensor (matrix) — a linear map that takes an integer index and returns a vector in ℝ⁵³⁷⁶. It's a lookup table with 262,144 rows, each row being a rank-1 tensor (vector) with 5,376 components. The result for a sequence of N tokens is a rank-2 tensor of shape `[N × 5,376]`.

### Step 3: Positional Encoding — Adding "Where" to "What"

The embedding vectors don't know their position in the sentence. **RoPE** (Rotary Position Encoding) modifies the Q and K vectors so that tokens know *where* they are relative to each other. Sliding attention layers use standard RoPE; full attention layers use **p-RoPE** (Proportional RoPE) which scales better to long contexts.

> **Math reference:** RoPE applies a rotation in ℝ² (pairs of dimensions) parameterized by position. Each pair of adjacent components in the Q and K vectors is rotated by an angle proportional to the token's position, so that dot(Q_i, K_j) naturally encodes relative distance |i - j|. This is a linear transformation in ℝ⁵³⁷⁶ that varies by position.

### Step 4: 60 Layers of Processing — The Core

Each of the 60 layers does two things: **attention** then **feed-forward**. The token vectors flow through all 60 layers sequentially, getting progressively refined.

> **Math reference:** Each layer is a function f: ℝ⁵³⁷⁶ → ℝ⁵³⁷⁶ applied independently to each token's vector. The full 60-layer stack is a composition f₆₀ ∘ f₅₉ ∘ ... ∘ f₁, transforming the embedding into a representation rich enough to predict the next token.

#### 4a. Attention — Tokens Talk to Each Other

Each token creates three vectors by multiplying its current vector by three learned weight matrices:

| Vector | How | Math |
|--------|-----|------|
| **Query (Q)** | "What am I looking for?" | Multiply vector in ℝ⁵³⁷⁶ by Q weight matrix → get vector in ℝ⁸¹⁹² (sliding) or ℝ¹⁶³⁸⁴ (full) |
| **Key (K)** | "What do I contain?" | Multiply vector in ℝ⁵³⁷⁶ by K weight matrix → get vector in ℝ⁴⁰⁹⁶ (sliding) or ℝ²⁰⁴⁸ (full) |
| **Value (V)** | "What information do I offer?" | Multiply vector in ℝ⁵³⁷⁶ by V weight matrix → get vector in ℝ⁴⁰⁹⁶ (sliding) or unified with K (full) |

> **Math reference:** Each weight matrix is a rank-2 tensor — a linear map between vector spaces. Q weight: ℝ⁵³⁷⁶ → ℝ⁸¹⁹² (sliding) or ℝ⁵³⁷⁶ → ℝ¹⁶³⁸⁴ (full). The 32 attention heads split the output into 32 parallel subspaces of ℝ²⁵⁶ (or ℝ⁵¹² for full attention), each computing attention independently.

Then each token's Q is compared against every other token's K to get **attention scores** — how much each token should listen to each other token. These scores weight the V vectors, producing a new context-rich vector for each token.

**Sliding attention** (50 layers): Each token only compares its Q against K vectors from the last 1,024 tokens. Cheap and local.

**Full attention** (10 layers): Each token compares its Q against *all* K vectors in the entire sequence. Expensive but captures long-range dependencies.

The 32 attention heads each do this independently in their own ℝ²⁵⁶ (or ℝ⁵¹²) subspace, then the results are concatenated and projected back to ℝ⁵³⁷⁶ by the O (output) matrix.

#### 4b. Feed-Forward Network — Processing the Context

After attention has gathered context, each token is processed individually through the FFN:

```
Token vector in ℝ⁵³⁷⁶
    → FFN up: multiply by [5376 × 21504] matrix → vector in ℝ²¹⁵⁰⁴  (expand)
    → FFN gate: multiply by [5376 × 21504] matrix → vector in ℝ²¹⁵⁰⁴  (gate)
    → multiply up × gate (element-wise, with activation)
    → FFN down: multiply by [21504 × 5376] matrix → vector in ℝ⁵³⁷⁶  (compress back)
```

> **Math reference:** The FFN is a composition of three linear maps with a non-linear activation. Up: ℝ⁵³⁷⁶ → ℝ²¹⁵⁰⁴ (rank-2 tensor, 115.6M scalars). Gate: ℝ⁵³⁷⁶ → ℝ²¹⁵⁰⁴ (rank-2 tensor, 115.6M scalars). The element-wise product in ℝ²¹⁵⁰⁴ is a non-linear operation (no matrix, just pointwise multiplication). Down: ℝ²¹⁵⁰⁴ → ℝ⁵³⁷⁶ (rank-2 tensor, 115.6M scalars). Total: ~347M scalars per FFN per layer.

The FFN expands each token from ℝ⁵³⁷⁶ into ℝ²¹⁵⁰⁴ (4× expansion), applies a non-linear activation, then compresses back to ℝ⁵³⁷⁶. This is where the model "thinks" about what it learned from attention — storing and retrieving knowledge.

#### 4c. Layer Norm and Residual

Each sub-layer (attention, FFN) is wrapped with:
- **Residual connection**: input + output (helps gradients flow during training, preserves information)
- **Layer norm**: normalizes the vector to keep values stable (a rank-1 tensor — a vector in ℝ⁵³⁷⁶ of learned scale factors)

> **Math reference:** Residual: output = f(x) + x, a direct addition of two vectors in ℝ⁵³⁷⁶. Layer norm: a rank-1 tensor (vector of 5,376 learned scale factors) that normalizes each component. These are the smallest parameters in the model — only 5,376 scalars each, stored as F32 (full precision) in all quantization variants.

### Step 5: Output Projection — Vectors → Next Token

After all 60 layers, each token's final vector in ℝ⁵³⁷⁶ is multiplied by the **output projection matrix**. Since word embeddings are tied with the output layer, this is the same `[262,144 × 5,376]` embedding matrix transposed — it maps from ℝ⁵³⁷⁶ back to ℝ²⁶²¹⁴⁴ (vocabulary space).

This produces a score for each of the 262,144 possible next tokens. The highest-scoring token (or a sampled one, depending on temperature) becomes the model's prediction.

> **Math reference:** The output projection is a linear map ℝ⁵³⁷⁶ → ℝ²⁶²¹⁴⁴, implemented as multiplication by the transposed embedding matrix (rank-2 tensor of shape `[5,376 × 262,144]`). The result is a vector in ℝ²⁶²¹⁴⁴ — one scalar per vocabulary token. The argmax (or sampling) of this vector selects the next token, reducing a rank-1 tensor to a rank-0 tensor (a single integer).

### Step 6: Autoregressive Generation — One Token at a Time

The model predicts **one token at a time**. Each predicted token is appended to the input, and the whole process repeats:

```
Prompt:     "Write a Python"           → predict "function"
Context:    "Write a Python function"   → predict "("
Context:    "Write a Python function("  → predict "n"
...and so on until a stop token is produced
```

This is why generation is slower than processing a prompt — each new token requires running through all 60 layers again. **KV caching** stores the K and V vectors from previous tokens so they don't need to be recomputed, but the new token still needs to attend to all previous tokens.

### The Full Pipeline in One Picture

```
Input text: "Write a Python function"
    │
    ▼
┌─────────────────────────┐
│  Tokenizer              │  Text → token IDs [4288, 452, 14952, 3450]
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  Embedding [262144×5376]│  Each ID → vector in ℝ⁵³⁷⁶
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  Layer 1 (sliding)      │  Attention (window=1024) + FFN (5376→21504→5376)
│  Layer 2 (sliding)      │  Attention + FFN
│  ...                    │
│  Layer 5 (FULL)         │  Attention (all tokens) + FFN  ← long-range context
│  ...                    │
│  Layer 59 (FULL)        │  Attention (all tokens) + FFN  ← final reasoning
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  Output projection      │  Vector in ℝ⁵³⁷⁶ → scores in ℝ²⁶²¹⁴⁴
│  (tied embedding)       │  Pick highest-scoring token
└─────────────────────────┘
    │
    ▼
Next token: "function"
```

### Where Quantization Fits

Quantization affects **Step 4** (the 60 layers) and **Step 2** (embedding). Each weight matrix is stored at reduced precision:

| Step | What's stored | Q8_0 | UD-Q8_K_XL |
|------|--------------|------|-------------|
| Embedding | `[262144 × 5376]` matrix | Q8_0 (8-bit) | Q8_0 (8-bit) |
| Q/K/V/O weights (most layers) | Various matrices | Q8_0 (8-bit) | Q8_0 (8-bit) |
| Q/K/FFN weights (layers 1, 52-59) | Various matrices | Q8_0 (8-bit) | **F16 (16-bit)** |
| Layer norms | Vectors in ℝ⁵³⁷⁶ | F32 (32-bit) | F32 (32-bit) |
| Output projection | Same as embedding (tied) | Q8_0 (8-bit) | Q8_0 (8-bit) |

The math is the same — vectors are still multiplied by matrices, projected between ℝⁿ spaces. Quantization just means each number in those matrices is stored with less precision (8 bits instead of 16 or 32), introducing small rounding errors that accumulate but barely affect output quality for Q8_0, and are mitigated in UD-Q8_K_XL by keeping the most critical layers at full F16 precision.

---

## Understanding CUDA

**CUDA** (Compute Unified Device Architecture) is NVIDIA's platform for running general-purpose computations on GPUs. It's what makes a GPU do more than just render graphics — it lets you run AI models, scientific simulations, and parallel math on the GPU.

### Why CUDA Matters Here

When you run `llama-cli` with `-ngl 99` (offload 99 layers to GPU), it means: **"Move all model weights from system RAM to the NVIDIA GPU's VRAM, and run all computations on the GPU."**

Without CUDA, you'd run the model on a CPU — which would be **50–100× slower** for transformer inference. An A100 processes tokens in milliseconds; a CPU would take seconds per token.

### The CUDA Stack

```
Your command (llama-cli, ollama, python)
      ↓
llama.cpp / PyTorch          ← Inference engine
      ↓
CUDA Runtime                 ← C/C++ library on the GPU
      ↓
NVIDIA GPU Driver            ← Kernel-level driver
      ↓
NVIDIA GPU Hardware          ← The actual chip (A100, RTX 4090, etc.)
```

- **llama.cpp / PyTorch** provides the inference engine that understands GGUF/safetensors formats
- **CUDA** translates operations (matrix multiplications, attention) into GPU instructions
- The **GPU** executes thousands of math operations in parallel

### Key Concepts

**Parallelism:** A GPU has thousands of cores. CUDA splits work across them — e.g., computing all 5,376 components of a token vector simultaneously, or multiplying a `[5376 × 8192]` weight matrix across thousands of tokens at once. This is why GPUs dominate AI workloads.

**VRAM (Video RAM):** The GPU's own memory, separate from system RAM. When you load a model with `-ngl 99`, model weights are copied from system RAM → VRAM. All computation then happens using VRAM. This is why quantization matters — Q8_0 needs ~30 GB VRAM for the 31B model, while Q4_0 needs ~16 GB.

**Quantization and VRAM:** CUDA supports multiple numeric formats. The GGUF format stores weights in Q4/Q8/F16 etc., but during inference llama.cpp dequantizes them on-the-fly as the GPU computes. The stored format determines VRAM usage; the computation format determines speed.

| Quantization | Weights stored as | VRAM needed (31B model) | Dequantized during compute? |
|---|---|---|---|
| Q4_0 | 4-bit integers | ~16 GB | Yes, to FP16 on GPU |
| Q8_0 | 8-bit integers | ~30 GB | Yes, to FP16 on GPU |
| UD-Q8_K_XL | Mix of 8-bit + F16 | ~33 GB | F16 layers stay as-is |
| BF16 (full) | 16-bit floats | ~65 GB | No dequantization needed |

### What Each Operation Uses

| Operation | Where it runs | Why |
|---|---|---|
| Model loading (download GGUF) | CPU + system RAM | Downloads and deserializes weights |
| `-ngl 99` (offload to GPU) | Copies weights to GPU VRAM | So inference runs on GPU |
| Tokenization | CPU | Simple text processing, no GPU needed |
| Embedding lookup | GPU via CUDA | Table lookup in `[262144 × 5376]` matrix |
| Attention (Q/K/V projections) | GPU via CUDA | Matrix multiplications across all tokens |
| Feed-forward network | GPU via CUDA | Matrix multiplications, 4× expansion |
| Output projection | GPU via CUDA | Final `[5376 × 262144]` matrix multiply |
| Sampling (temperature, top-k) | CPU | Simple probability operations on 262K values |

### Without CUDA

- `-ngl 99` → **error** if no NVIDIA GPU is present
- You *can* run on CPU with `-ngl 0`, but generation would take **seconds per token** instead of milliseconds
- There's no real alternative for production inference — AMD has ROCm, Apple has Metal, but the ecosystem (llama.cpp, PyTorch, Flash Attention) is CUDA-first

---

## Links
>>>>>>> REPLACE`

- [Google Gemma 4 31B IT (base)](https://hf.co/google/gemma-4-31B-it)
- [Google QAT Q4_0 GGUF](https://hf.co/google/gemma-4-31B-it-qat-q4_0-gguf)
- [Google QAT W4A16 compressed-tensors](https://hf.co/google/gemma-4-31B-it-qat-w4a16-ct)
- [Google QAT unquantized](https://hf.co/google/gemma-4-31B-it-qat-q4_0-unquantized)
- [Unsloth GGUF (all quantizations)](https://hf.co/unsloth/gemma-4-31B-it-GGUF)
- [Unsloth QAT GGUF](https://hf.co/unsloth/gemma-4-31B-it-qat-GGUF)
