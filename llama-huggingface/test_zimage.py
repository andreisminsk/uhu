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