#!/usr/bin/env python3
"""Gemma 4 31B IT inference via llama-cpp-python on Win11 CPU-only laptop.

Based on test_lcpp_gemma4.py, adapted for the 31B model.
Uses GGUF quantized models with llama.cpp for efficient CPU inference.

The 31B model is significantly larger than the 12B — ensure you have enough RAM.
Official Google QAT (Quantization-Aware Training) GGUF is the primary option.
Community quantizations from bartowski are also available.

Requirements:
    pip install llama-cpp-python huggingface-hub

For GPU acceleration (if you later get a CUDA GPU):
    pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu126
"""

import sys
import os
import argparse

# ─── Configuration ────────────────────────────────────────────────────────

# GGUF quantization options for Gemma 4 31B IT
# The 31B model is ~2.5x larger than 12B, so RAM requirements are much higher.
# Official Google QAT Q4_0 is the primary option; community quants from bartowski
# provide additional choices.
GGUF_OPTIONS = {
    "Q3_K_M":  {"size": "~12 GB", "ram": "~16 GB", "quality": "Low",       "note": "Smallest, fastest, noticeable quality loss"},
    "Q4_0":    {"size": "~17 GB", "ram": "~20 GB", "quality": "Decent",     "note": "Official Google QAT Q4_0 — recommended sweet spot"},
    "Q4_K_M":  {"size": "~19 GB", "ram": "~23 GB", "quality": "Decent+",    "note": "Community quant, good balance"},
    "Q4_K_S":  {"size": "~17 GB", "ram": "~20 GB", "quality": "Decent",     "note": "Community quant, slightly smaller than Q4_K_M"},
    "Q5_K_M":  {"size": "~22 GB", "ram": "~26 GB", "quality": "Good",       "note": "Better quality, needs 32+ GB RAM"},
    "Q6_K":    {"size": "~26 GB", "ram": "~30 GB", "quality": "Very Good",  "note": "Close to FP16, needs 32+ GB RAM"},
    "Q8_0":    {"size": "~33 GB", "ram": "~37 GB", "quality": "Excellent",   "note": "Near-original quality, needs 64 GB RAM"},
}

# Official Google QAT GGUF repo (Q4_0 only)
OFFICIAL_REPO = "google/gemma-4-31B-it-qat-q4_0-gguf"

# Community GGUF repo (multiple quantization levels)
COMMUNITY_REPO = "bartowski/gemma-4-31B-it-GGUF"

# Exact GGUF filenames on HuggingFace
GGUF_FILENAMES = {
    # Official Google QAT
    "Q4_0":   {"repo": OFFICIAL_REPO,   "filename": "gemma-4-31B_q4_0-it.gguf"},
    # Community (bartowski) — may not all be available yet
    "Q3_K_M": {"repo": COMMUNITY_REPO,  "filename": "gemma-4-31B-it-Q3_K_M.gguf"},
    "Q4_K_M": {"repo": COMMUNITY_REPO,  "filename": "gemma-4-31B-it-Q4_K_M.gguf"},
    "Q4_K_S": {"repo": COMMUNITY_REPO,  "filename": "gemma-4-31B-it-Q4_K_S.gguf"},
    "Q5_K_M": {"repo": COMMUNITY_REPO,  "filename": "gemma-4-31B-it-Q5_K_M.gguf"},
    "Q6_K":   {"repo": COMMUNITY_REPO,  "filename": "gemma-4-31B-it-Q6_K.gguf"},
    "Q8_0":   {"repo": COMMUNITY_REPO,  "filename": "gemma-4-31B-it-Q8_0.gguf"},
}

# Multimodal projector file (needed for vision input)
MMPROJ_FILENAME = "gemma-4-31B-it-mmproj.gguf"

DEFAULT_QUANT = "Q4_0"
DEFAULT_CONTEXT = 4096  # Lower default for 31B to fit in RAM
DEFAULT_THREADS = 0  # 0 = auto-detect (uses physical cores)

# ─── Helpers ─────────────────────────────────────────────────────────────

def detect_threads():
    """Detect optimal thread count for CPU inference."""
    try:
        # Physical cores are best for llama.cpp
        import psutil
        physical = psutil.cpu_count(logical=False)
        logical = psutil.cpu_count(logical=True)
        return physical or logical or 4
    except ImportError:
        import multiprocessing
        return multiprocessing.cpu_count()


def download_model(quant: str) -> tuple:
    """Download GGUF model and mmproj from HuggingFace if not cached locally.
    
    Returns:
        Tuple of (model_path, mmproj_path). mmproj_path may be None if not found.
    """
    from huggingface_hub import hf_hub_download

    entry = GGUF_FILENAMES.get(quant)
    if not entry:
        print(f"❌ No known filename for quantization {quant}")
        print(f"   Available: {', '.join(GGUF_FILENAMES.keys())}")
        sys.exit(1)

    repo = entry["repo"]
    filename = entry["filename"]

    # Download main model
    try:
        print(f"📥 Downloading {filename} from {repo}...")
        model_path = hf_hub_download(
            repo_id=repo,
            filename=filename,
        )
    except Exception as e:
        print(f"❌ Download failed: {e}")
        print(f"\n   Download manually from:")
        print(f"   https://huggingface.co/{repo}/resolve/main/{filename}")
        print(f"   Then run with: --model <path_to_file>")
        sys.exit(1)

    # Download mmproj (multimodal projector for vision)
    mmproj_path = None
    try:
        print(f"📥 Downloading {MMPROJ_FILENAME} (multimodal projector)...")
        mmproj_path = hf_hub_download(
            repo_id=OFFICIAL_REPO,
            filename=MMPROJ_FILENAME,
        )
    except Exception as e:
        print(f"⚠️  Could not download mmproj: {e}")
        print(f"   Vision input will not be available (text-only mode).")
        mmproj_path = None

    return model_path, mmproj_path


def find_local_model(quant: str, model_dir: str = None) -> tuple:
    """Find local GGUF model and mmproj files.
    
    Returns:
        Tuple of (model_path, mmproj_path). Either may be None.
    """
    search_dirs = [model_dir] if model_dir else [
        os.path.expanduser("~/.cache/huggingface/hub"),
        os.path.expanduser("~/.ollama/models"),
        os.path.dirname(os.path.abspath(__file__)),
    ]

    model_path = None
    mmproj_path = None

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            for f in files:
                if f.endswith(".gguf") and quant.lower().replace("_", "").replace("k", "k") in f.lower().replace("_", "").replace("-", ""):
                    if "mmproj" not in f.lower():
                        model_path = os.path.join(root, f)
                if f.endswith(".gguf") and "mmproj" in f.lower() and "31b" in f.lower():
                    mmproj_path = os.path.join(root, f)

    return model_path, mmproj_path


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gemma 4 31B IT inference via llama-cpp-python (CPU-optimized for Win11)"
    )
    parser.add_argument("--model", type=str, default=None,
                        help="Path to local .gguf model file (skips download)")
    parser.add_argument("--mmproj", type=str, default=None,
                        help="Path to local mmproj.gguf file for vision support")
    parser.add_argument("--quant", type=str, default=DEFAULT_QUANT,
                        choices=list(GGUF_OPTIONS.keys()),
                        help=f"Quantization level (default: {DEFAULT_QUANT})")
    parser.add_argument("--context", type=int, default=DEFAULT_CONTEXT,
                        help=f"Context window size (default: {DEFAULT_CONTEXT})")
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS,
                        help="Number of CPU threads (default: auto-detect)")
    parser.add_argument("--max-tokens", type=int, default=1024,
                        help="Max tokens to generate (default: 1024)")
    parser.add_argument("--temperature", type=float, default=0.7,
                        help="Sampling temperature (default: 0.7)")
    parser.add_argument("--top-p", type=float, default=0.9,
                        help="Top-p sampling (default: 0.9)")
    parser.add_argument("--prompt", type=str, default=None,
                        help="Custom prompt (default: built-in test prompt)")
    parser.add_argument("--interactive", action="store_true",
                        help="Start interactive chat mode")
    parser.add_argument("--gpu-layers", type=int, default=0,
                        help="Layers to offload to GPU (0=CPU-only, default: 0)")
    args = parser.parse_args()

    # ── Show quantization info ────────────────────────────────────────────
    print("\n📊 GGUF Quantization Options for Gemma 4 31B IT:\n")
    print(f"  {'Quant':<10} {'Size':<10} {'RAM Need':<12} {'Quality':<12} Note")
    print(f"  {'─'*10} {'─'*10} {'─'*12} {'─'*12} {'─'*40}")
    for q, info in GGUF_OPTIONS.items():
        marker = " ◀ selected" if q == args.quant else ""
        print(f"  {q:<10} {info['size']:<10} {info['ram']:<12} {info['quality']:<12} {info['note']}{marker}")
    print()
    print("⚠️  Note: The 31B model requires significantly more RAM than the 12B.")
    print("   Q4_0 needs ~20 GB RAM. Consider the 12B model for 16 GB laptops.\n")

    # ── Resolve threads ──────────────────────────────────────────────────
    n_threads = args.threads or detect_threads()
    print(f"🔧 Using {n_threads} CPU threads")

    # ── Resolve model path ───────────────────────────────────────────────
    mmproj_path = args.mmproj

    if args.model:
        model_path = args.model
        if not os.path.isfile(model_path):
            print(f"❌ Model file not found: {model_path}")
            sys.exit(1)
    else:
        # Try to find locally first
        model_path, found_mmproj = find_local_model(args.quant)
        if model_path:
            print(f"📦 Found local model: {model_path}")
            if found_mmproj and not mmproj_path:
                mmproj_path = found_mmproj
                print(f"📦 Found local mmproj: {mmproj_path}")
        else:
            print(f"📥 No local model found for {args.quant}. Downloading...")
            model_path, found_mmproj = download_model(args.quant)
            if found_mmproj and not mmproj_path:
                mmproj_path = found_mmproj

    print(f"📁 Model: {model_path}")
    print(f"📁 MMPROJ: {mmproj_path or 'Not found (text-only mode)'}")
    print(f"🎯 Quantization: {args.quant}")
    print(f"📏 Context: {args.context} tokens")
    print()

    # ── Load model ───────────────────────────────────────────────────────
    try:
        from llama_cpp import Llama
    except ImportError:
        print("❌ llama-cpp-python not installed. Install with:")
        print("   pip install llama-cpp-python")
        print("\n   For CUDA GPU support:")
        print("   pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu126")
        sys.exit(1)

    print("⏳ Loading model (this may take a few minutes for 31B)...")
    try:
        load_kwargs = dict(
            model_path=model_path,
            n_ctx=args.context,
            n_threads=n_threads,
            n_gpu_layers=args.gpu_layers,
            verbose=False,
        )
        # Add mmproj for multimodal support if available
        if mmproj_path:
            load_kwargs["mmproj"] = mmproj_path

        llm = Llama(**load_kwargs)
    except ValueError as e:
        print(f"\n❌ Failed to load model: {e}")
        print(f"\n💡 This is usually an out-of-memory error. Try reducing context size:")
        print(f"   Current: --context {args.context}")
        print(f"   Suggested: --context {min(args.context, 2048)}")
        print(f"\n   RAM estimates for Q4_0 (~20 GB model weights + KV cache):")
        print(f"     --context 2048  → ~21 GB total")
        print(f"     --context 4096  → ~22 GB total")
        print(f"     --context 8192  → ~24 GB total")
        print(f"     --context 32768 → ~30+ GB total (needs 32+ GB RAM)")
        sys.exit(1)
    print("✅ Model loaded!\n")

    # ── Default test prompt ──────────────────────────────────────────────
    default_prompt = "Explain the significance of the Silk Road in 3 paragraphs."
    prompt = args.prompt or default_prompt

    # ── Interactive or single-shot ───────────────────────────────────────
    if args.interactive:
        print("💬 Interactive chat mode (type 'quit' to exit, 'clear' to reset)\n")
        messages = []
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Bye!")
                break

            if user_input.lower() == "quit":
                print("👋 Bye!")
                break
            if user_input.lower() == "clear":
                messages = []
                print("🔄 Conversation cleared.\n")
                continue
            if not user_input:
                continue

            messages.append({"role": "user", "content": user_input})

            print("Assistant: ", end="", flush=True)
            response = llm.create_chat_completion(
                messages=messages,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                top_p=args.top_p,
                stream=True,
            )

            full_response = ""
            for chunk in response:
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    print(content, end="", flush=True)
                    full_response += content
            print("\n")

            messages.append({"role": "assistant", "content": full_response})
    else:
        # Single-shot generation
        print(f"📝 Prompt: {prompt}\n")
        print("⏳ Generating...\n")

        response = llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
        )

        answer = response["choices"][0]["message"]["content"]
        print(f"Response:\n{answer}")

        # Show stats
        usage = response.get("usage", {})
        if usage:
            print(f"\n📊 Tokens — Prompt: {usage.get('prompt_tokens', '?')}, "
                  f"Completion: {usage.get('completion_tokens', '?')}, "
                  f"Total: {usage.get('total_tokens', '?')}")


if __name__ == "__main__":
    main()
