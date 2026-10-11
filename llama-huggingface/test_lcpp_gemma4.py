#!/usr/bin/env python3
"""Gemma 4 12B IT inference via llama-cpp-python on Win11 CPU-only laptop.

Based on Option 3 from GEMMA4-WIN11-EXPERIMENT.md.
Uses GGUF quantized models with llama.cpp for efficient CPU inference.

Requirements:
    pip install llama-cpp-python huggingface-hub

For GPU acceleration (if you later get a CUDA GPU):
    pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu126
"""

import sys
import os
import argparse

# ─── Configuration ────────────────────────────────────────────────────────

# GGUF quantization options for Gemma 4 12B IT
# Smaller = faster + less RAM, but lower quality
GGUF_OPTIONS = {
    "Q3_K_M":  {"size": "~5 GB",  "ram": "~7 GB",  "quality": "Low",      "note": "Smallest, fastest, noticeable quality loss"},
    "Q4_K_M":  {"size": "~7 GB",  "ram": "~10 GB", "quality": "Decent",   "note": "Sweet spot for 16 GB laptops"},
    "Q4_K_S":  {"size": "~6 GB",  "ram": "~9 GB",  "quality": "Decent-",  "note": "Slightly smaller than Q4_K_M"},
    "Q5_K_M":  {"size": "~8 GB",  "ram": "~11 GB", "quality": "Good",     "note": "Better quality, needs more RAM"},
    "Q6_K":    {"size": "~10 GB", "ram": "~13 GB", "quality": "Very Good", "note": "Close to FP16 quality"},
    "Q8_0":    {"size": "~12 GB", "ram": "~15 GB", "quality": "Excellent", "note": "Near-original quality, needs 16+ GB RAM"},
}

MODEL_REPO = "bartowski/gemma-4-12B-it-GGUF"

# Exact GGUF filenames on HuggingFace
GGUF_FILENAMES = {
    "Q3_K_M": "gemma-4-12B-it-Q3_K_M.gguf",
    "Q4_K_M": "gemma-4-12B-it-Q4_K_M.gguf",
    "Q4_K_S": "gemma-4-12B-it-Q4_K_S.gguf",
    "Q5_K_M": "gemma-4-12B-it-Q5_K_M.gguf",
    "Q6_K":   "gemma-4-12B-it-Q6_K.gguf",
    "Q8_0":   "gemma-4-12B-it-Q8_0.gguf",
}

DEFAULT_QUANT = "Q4_K_M"
DEFAULT_CONTEXT = 8192
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


def download_model(quant: str) -> str:
    """Download GGUF model from HuggingFace if not cached locally."""
    from huggingface_hub import hf_hub_download

    filename = GGUF_FILENAMES.get(quant)
    if not filename:
        print(f"❌ No known filename for quantization {quant}")
        print(f"   Available: {', '.join(GGUF_FILENAMES.keys())}")
        sys.exit(1)

    try:
        print(f"📥 Downloading {filename} from {MODEL_REPO}...")
        path = hf_hub_download(
            repo_id=MODEL_REPO,
            filename=filename,
        )
        return path
    except Exception as e:
        print(f"❌ Download failed: {e}")
        print(f"\n   Download manually from:")
        print(f"   https://huggingface.co/{MODEL_REPO}/resolve/main/{filename}")
        print(f"   Then run with: --model <path_to_file>")
        sys.exit(1)


def find_local_model(quant: str, model_dir: str = None) -> str:
    """Find a local GGUF model file."""
    search_dirs = [model_dir] if model_dir else [
        os.path.expanduser("~/.cache/huggingface/hub"),
        os.path.expanduser("~/.ollama/models"),
        os.path.dirname(os.path.abspath(__file__)),
    ]

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            for f in files:
                if f.endswith(".gguf") and quant.lower() in f.lower():
                    return os.path.join(root, f)
    return None


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gemma 4 12B IT inference via llama-cpp-python (CPU-optimized for Win11)"
    )
    parser.add_argument("--model", type=str, default=None,
                        help="Path to local .gguf model file (skips download)")
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
    print("\n📊 GGUF Quantization Options for Gemma 4 12B IT:\n")
    print(f"  {'Quant':<10} {'Size':<10} {'RAM Need':<12} {'Quality':<12} Note")
    print(f"  {'─'*10} {'─'*10} {'─'*12} {'─'*12} {'─'*40}")
    for q, info in GGUF_OPTIONS.items():
        marker = " ◀ selected" if q == args.quant else ""
        print(f"  {q:<10} {info['size']:<10} {info['ram']:<12} {info['quality']:<12} {info['note']}{marker}")
    print()

    # ── Resolve threads ──────────────────────────────────────────────────
    n_threads = args.threads or detect_threads()
    print(f"🔧 Using {n_threads} CPU threads")

    # ── Resolve model path ───────────────────────────────────────────────
    if args.model:
        model_path = args.model
        if not os.path.isfile(model_path):
            print(f"❌ Model file not found: {model_path}")
            sys.exit(1)
    else:
        # Try to find locally first
        model_path = find_local_model(args.quant)
        if model_path:
            print(f"📦 Found local model: {model_path}")
        else:
            print(f"📥 No local model found for {args.quant}. Downloading...")
            model_path = download_model(args.quant)

    print(f"📁 Model: {model_path}")
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

    print("⏳ Loading model (this may take a minute)...")
    try:
        llm = Llama(
            model_path=model_path,
            n_ctx=args.context,
            n_threads=n_threads,
            n_gpu_layers=args.gpu_layers,
            verbose=False,
        )
    except ValueError as e:
        print(f"\n❌ Failed to load model: {e}")
        print(f"\n💡 This is usually an out-of-memory error. Try reducing context size:")
        print(f"   Current: --context {args.context}")
        print(f"   Suggested: --context {min(args.context, 4096)}")
        print(f"\n   RAM estimates for Q4_K_M (~10 GB model weights + KV cache):")
        print(f"     --context 4096  → ~11 GB total")
        print(f"     --context 8192  → ~12 GB total")
        print(f"     --context 32768 → ~16+ GB total (may fail on 16 GB laptops)")
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
