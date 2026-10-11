#!/usr/bin/env python3
"""Gemma 4 12B IT inference using HuggingFace Transformers with quantization support"""

import sys
import torch

# Workaround: transformers 4.57.x has a bug where Gemma 4's extra_special_tokens
# is a list but TokenizerMixin expects a dict. Patch it before loading.
import transformers.tokenization_utils_base as _tub
_orig_set = _tub.PreTrainedTokenizerBase._set_model_specific_special_tokens

def _patched_set(self, special_tokens=None):
    if isinstance(special_tokens, list):
        special_tokens = {}
    _orig_set(self, special_tokens=special_tokens)

_tub.PreTrainedTokenizerBase._set_model_specific_special_tokens = _patched_set

from transformers import AutoModelForCausalLM, AutoTokenizer

# ─── Quantization Options ───────────────────────────────────────────────
# Choose quantization level based on your GPU VRAM / system RAM:
#
#   Option  | Precision   | Approx VRAM/RAM  | Quality  | Speed
#   --------|-------------|-------------------|----------|-------
#   0       | BF16        | ~24 GB            | Best     | Fastest
#   1       | FP16        | ~24 GB            | Best     | Fastest
#   2       | 8-bit       | ~13 GB            | Good     | Moderate
#   3       | 4-bit NF4   | ~7 GB             | Decent   | Slower
#   4       | 4-bit FP4   | ~7 GB             | Decent   | Slower
#
# For 16 GB VRAM: use option 2 (8-bit) or 3/4 (4-bit)
# For 8 GB VRAM:  use option 3 or 4 (4-bit) with short context
# For 24+ GB VRAM: use option 0 or 1 (full precision)

QUANTIZATION_OPTIONS = {
    0: {"name": "BF16 (full precision)",  "dtype": torch.bfloat16, "bnb": None},
    1: {"name": "FP16 (full precision)",  "dtype": torch.float16,  "bnb": None},
    2: {"name": "8-bit (bitsandbytes)",    "dtype": torch.float16,  "bnb": "load_in_8bit"},
    3: {"name": "4-bit NF4 (bitsandbytes)","dtype": torch.float16,  "bnb": "nf4"},
    4: {"name": "4-bit FP4 (bitsandbytes)","dtype": torch.float16,  "bnb": "fp4"},
}

def check_bitsandbytes():
    """Check if bitsandbytes is installed and return True if available."""
    try:
        import importlib.metadata
        importlib.metadata.version("bitsandbytes")
        return True
    except importlib.metadata.PackageNotFoundError:
        return False

_BNB_AVAILABLE = check_bitsandbytes()

def get_bnb_config(bnb_mode):
    """Lazy-import bitsandbytes and create quantization config only when needed."""
    if bnb_mode is None:
        return None
    if not _BNB_AVAILABLE:
        raise RuntimeError(
            "bitsandbytes is not installed. Install it with: pip install bitsandbytes\n"
            "Or select option 0 (BF16) or 1 (FP16) which don't require it."
        )
    from transformers import BitsAndBytesConfig
    if bnb_mode == "load_in_8bit":
        return BitsAndBytesConfig(load_in_8bit=True)
    elif bnb_mode == "nf4":
        return BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16)
    elif bnb_mode == "fp4":
        return BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="fp4", bnb_4bit_compute_dtype=torch.bfloat16)
    else:
        raise ValueError(f"Unknown bnb_mode: {bnb_mode}")

# ─── Select Quantization ────────────────────────────────────────────────
print("Available quantization options:\n")
for key, opt in QUANTIZATION_OPTIONS.items():
    suffix = "" if opt["bnb"] is None or _BNB_AVAILABLE else "  ⚠️ bitsandbytes not installed"
    print(f"  [{key}] {opt['name']}{suffix}")
if not _BNB_AVAILABLE:
    print("\n⚠️  bitsandbytes not installed — options 2-4 require it.")
    print("   Install with: pip install bitsandbytes")
    print("   Or use option 0 (BF16) / 1 (FP16) which don't need it.")
print()

try:
    choice = int(input(f"Select quantization (0-{max(QUANTIZATION_OPTIONS.keys())}, default=3): ") or "3")
    if choice not in QUANTIZATION_OPTIONS:
        print(f"Invalid choice '{choice}', defaulting to 3 (4-bit NF4)")
        choice = 3
except ValueError:
    choice = 3

quant = QUANTIZATION_OPTIONS[choice]
print(f"\nUsing: {quant['name']}\n")

# ─── Load Model and Tokenizer ───────────────────────────────────────────
model_id = "google/gemma-4-12B-it"

tokenizer = AutoTokenizer.from_pretrained(model_id)

load_kwargs = {
    "torch_dtype": quant["dtype"],
    "device_map": "auto",
}
bnb_config = get_bnb_config(quant["bnb"])
if bnb_config is not None:
    load_kwargs["quantization_config"] = bnb_config

model = AutoModelForCausalLM.from_pretrained(model_id, **load_kwargs)

# Optional: enable thinking/reasoning mode
# model.config.enable_thinking = True

# ─── Prepare Conversation ───────────────────────────────────────────────
messages = [
    {"role": "user", "content": "Explain the significance of the Silk Road in 3 paragraphs."},
]

inputs = tokenizer.apply_chat_template(
    messages,
    tokenize=True,
    add_generation_prompt=True,
    return_tensors="pt",
).to(model.device)

# ─── Generate ────────────────────────────────────────────────────────────
print("Generating response...\n")

with torch.no_grad():
    outputs = model.generate(
        inputs,
        max_new_tokens=1024,
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
    )

response = tokenizer.decode(outputs[0][inputs.shape[-1]:], skip_special_tokens=True)
print(f"Response:\n{response}")
