"""TEST DOUBLE for inference_scripts/controlnet_refine.py. It does NOT run Stable Diffusion.

Mirrors the real script's arguments and console output and writes a coloured
image derived from the control map. FAKE_CONTROLNET_MODE: ok, oom, missing_weights,
no_output, hang.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from PIL import Image, ImageOps

parser = argparse.ArgumentParser()
for name in ("--control", "--output", "--prompt", "--negative-prompt", "--base-model", "--controlnet-model", "--memory"):
    parser.add_argument(name, default="")
parser.add_argument("--steps", type=int, default=20)
parser.add_argument("--guidance", type=float, default=7.5)
parser.add_argument("--conditioning-scale", type=float, default=1.0)
parser.add_argument("--seed", type=int, default=42)
args = parser.parse_args()
mode = os.environ.get("FAKE_CONTROLNET_MODE", "ok")
Path(args.output).with_name("controlnet_argv.json").write_text(json.dumps(sys.argv[1:]), encoding="utf-8")

print("Loading ControlNet models ...", flush=True)
if mode == "missing_weights":
    print("OSError: We couldn't connect to 'https://huggingface.co' to load this model", file=sys.stderr)
    sys.exit(1)
for step in range(1, args.steps + 1):
    print(f"ControlNet step {step}/{args.steps}", flush=True)
    if mode == "oom" and step == 3:
        print("torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 512.00 MiB", file=sys.stderr)
        sys.exit(1)
    if mode == "hang":
        time.sleep(3600)
if mode == "no_output":
    sys.exit(0)
strokes = Image.open(args.control).convert("L")
ImageOps.colorize(ImageOps.invert(strokes), black="#5a3a1a", white="#ffffff").save(args.output)
print(json.dumps({"output": args.output, "memory_mode": "offload", "device": "Test GPU", "vram_gb": 6.0}))
