"""
GGUF Model Inspector — Download and analyze per-tensor quantization details.

Usage:
    python inspect_gguf.py --model unsloth/gemma-4-31B-it-GGUF --quant UD-Q8_K_XL
    python inspect_gguf.py --model unsloth/gemma-4-31B-it-GGUF --quant Q8_0
    python inspect_gguf.py --local /path/to/model.gguf

Requirements:
    pip install huggingface-hub gguf
"""

import argparse
import sys
import os
from collections import defaultdict
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

def download_model(repo_id: str, quant: str, cache_dir: str = None) -> str:
    """Download a GGUF model from HuggingFace."""
    from huggingface_hub import hf_hub_download

    # Map quant names to filenames
    filename = f"gemma-4-31B-it-{quant}.gguf"

    print(f"Downloading {filename} from {repo_id}...")
    print(f"File size: ~35 GB for UD-Q8_K_XL, may take a while.\n")

    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        cache_dir=cache_dir,
        resume_download=True,
    )
    print(f"Downloaded to: {path}\n")
    return path


def inspect_gguf(filepath: str) -> None:
    """Parse GGUF file and print per-tensor quantization details."""
    from gguf import GGUFReader

    print(f"Inspecting: {filepath}")
    print(f"File size: {os.path.getsize(filepath) / (1024**3):.2f} GB\n")

    reader = GGUFReader(filepath)

    # ── Metadata ──
    print("=" * 80)
    print("MODEL METADATA")
    print("=" * 80)

    arch = None
    for key, value in reader.fields.items():
        # Print key architecture fields
        if key in (
            "general.architecture",
            "general.name",
            "gemma4.context_length",
            "gemma4.embedding_length",
            "gemma4.feed_forward_length",
            "gemma4.block_count",
            "gemma4.attention.head_count",
            "gemma4.attention.head_count_kv",
            "gemma4.attention.layer_norm_rms_epsilon",
            "gemma4.vocab_size",
        ):
            val = value
            if hasattr(value, "parts"):
                val = value.parts[0] if value.parts else value
            print(f"  {key}: {val}")
        if key == "general.architecture":
            arch = value
            if hasattr(value, "parts"):
                arch = value.parts[0]

    print()

    # ── Per-tensor quantization ──
    print("=" * 80)
    print("PER-TENSOR QUANTIZATION")
    print("=" * 80)

    # Group tensors by type
    type_stats = defaultdict(lambda: {"count": 0, "total_bytes": 0, "tensors": []})

    # Sort tensors by name for consistent output
    sorted_tensors = sorted(reader.tensors, key=lambda t: t.name)

    # Track layer info
    layer_types = {}  # layer_num -> set of quant types

    print(f"\n{'Tensor Name':<55} {'Type':<10} {'Shape':<25} {'Size (MB)':>10}")
    print("-" * 105)

    total_size = 0
    for tensor in sorted_tensors:
        name = tensor.name
        ttype = tensor.tensor_type.name if hasattr(tensor.tensor_type, "name") else str(tensor.tensor_type)
        shape = str(list(tensor.shape)) if hasattr(tensor, "shape") else "N/A"
        size_bytes = tensor.n_bytes
        size_mb = size_bytes / (1024 * 1024)
        total_size += size_bytes

        type_stats[ttype]["count"] += 1
        type_stats[ttype]["total_bytes"] += size_bytes
        type_stats[ttype]["tensors"].append(name)

        # Track per-layer quantization
        if "blk." in name:
            try:
                layer_num = int(name.split("blk.")[1].split(".")[0])
                if layer_num not in layer_types:
                    layer_types[layer_num] = {}
                layer_types[layer_num][name] = ttype
            except (ValueError, IndexError):
                pass

        print(f"{name:<55} {ttype:<10} {shape:<25} {size_mb:>10.2f}")

    print("-" * 105)
    print(f"{'TOTAL':<55} {'':10} {'':25} {total_size / (1024*1024):>10.2f}")

    # ── Summary by quantization type ──
    print("\n" + "=" * 80)
    print("SUMMARY BY QUANTIZATION TYPE")
    print("=" * 80)
    print(f"\n{'Type':<15} {'Count':>6} {'Total (GB)':>12} {'% of Model':>12}")
    print("-" * 50)

    for ttype, stats in sorted(type_stats.items(), key=lambda x: -x[1]["total_bytes"]):
        pct = (stats["total_bytes"] / total_size) * 100
        gb = stats["total_bytes"] / (1024**3)
        print(f"{ttype:<15} {stats['count']:>6} {gb:>12.3f} {pct:>11.1f}%")

    print("-" * 50)
    print(f"{'TOTAL':<15} {sum(s['count'] for s in type_stats.values()):>6} {total_size / (1024**3):>12.3f} {'100.0%':>12}")

    # ── Per-layer quantization breakdown ──
    if layer_types:
        print("\n" + "=" * 80)
        print("PER-LAYER QUANTIZATION (attention + MLP per decoder layer)")
        print("=" * 80)

        # Determine which layers are full_attention vs sliding_attention
        # Gemma 4 31B: full_attention at layers 5,11,17,23,29,35,41,47,53,59
        full_attn_layers = {5, 11, 17, 23, 29, 35, 41, 47, 53, 59}

        print(f"\n{'Layer':>5} {'Type':<20} {'Q':>4} {'K':>4} {'V':>4} {'O':>4} {'FFN_up':>8} {'FFN_gate':>8} {'FFN_down':>8}")
        print("-" * 80)

        for layer_num in sorted(layer_types.keys()):
            tensors = layer_types[layer_num]
            attn_type = "full_attention" if layer_num in full_attn_layers else "sliding_attention"

            def get_type(prefix):
                for name, ttype in tensors.items():
                    if prefix in name:
                        return ttype
                return "—"

            q_type = get_type("attn_q")
            k_type = get_type("attn_k")
            v_type = get_type("attn_v")
            o_type = get_type("attn_output") or get_type("attn_o")
            ffn_up = get_type("ffn_up")
            ffn_gate = get_type("ffn_gate")
            ffn_down = get_type("ffn_down")

            print(f"{layer_num:>5} {attn_type:<20} {q_type:>4} {k_type:>4} {v_type:>4} {o_type:>4} {ffn_up:>8} {ffn_gate:>8} {ffn_down:>8}")

    # ── Comparison helper ──
    print("\n" + "=" * 80)
    print("NOTES")
    print("=" * 80)
    print("""
Compare with another quantization by running this script again with a different --quant flag.
For example:
    python inspect_gguf.py --model unsloth/gemma-4-31B-it-GGUF --quant Q8_0
    python inspect_gguf.py --model unsloth/gemma-4-31B-it-GGUF --quant UD-Q4_K_XL

Key quantization types:
    F32      — 32-bit float (uncompressed)
    F16      — 16-bit float (half precision)
    Q8_0     — 8-bit quantization (essentially lossless)
    Q6_K     — 6-bit K-quant (near-lossless)
    Q5_K     — 5-bit K-quant (good quality)
    Q4_K     — 4-bit K-quant (balanced)
    Q3_K     — 3-bit K-quant (aggressive compression)
    IQ types — Importance-matrix variants with non-linear quantization
""")


def main():
    parser = argparse.ArgumentParser(description="Download and inspect GGUF model quantization details")
    parser.add_argument("--model", type=str, default="unsloth/gemma-4-31B-it-GGUF",
                        help="HuggingFace repo ID (default: unsloth/gemma-4-31B-it-GGUF)")
    parser.add_argument("--quant", type=str, default="UD-Q8_K_XL",
                        help="Quantization variant (e.g., UD-Q8_K_XL, Q8_0, UD-Q4_K_XL)")
    parser.add_argument("--local", type=str, default=None,
                        help="Path to local GGUF file (skip download)")
    parser.add_argument("--cache-dir", type=str, default=None,
                        help="HuggingFace cache directory (default: ~/.cache/huggingface)")

    args = parser.parse_args()

    if args.local:
        filepath = args.local
    else:
        filepath = download_model(args.model, args.quant, args.cache_dir)

    inspect_gguf(filepath)


if __name__ == "__main__":
    main()
