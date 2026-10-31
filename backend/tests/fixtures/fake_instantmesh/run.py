"""TEST DOUBLE for TencentARC InstantMesh's run.py. It does NOT reconstruct anything.

It mirrors the official CLI arguments, console messages and output layout
(<output>/<config>/images/<name>.png and <output>/<config>/meshes/<name>.obj)
and always writes the same Z-up, vertex-coloured box, so the backend pipeline can
be exercised without a GPU. FAKE_INSTANTMESH_MODE selects failure behaviour:
ok, oom, crash, missing_weights, no_output, nan, hang. FAKE_INSTANTMESH_STEP_DELAY
slows the fake diffusion loop (seconds per step).
"""
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("config")
parser.add_argument("input_path")
parser.add_argument("--output_path", default="outputs/")
parser.add_argument("--diffusion_steps", type=int, default=75)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--no_rembg", action="store_true")
parser.add_argument("--export_texmap", action="store_true")
args = parser.parse_args()
mode = os.environ.get("FAKE_INSTANTMESH_MODE", "ok")
if mode == "oom_large_only":  # simulates a small GPU: only the large config runs out of memory
    mode = "oom" if "large" in Path(args.config).stem else "ok"
delay = float(os.environ.get("FAKE_INSTANTMESH_STEP_DELAY", "0"))
config_name = Path(args.config).stem
name = Path(args.input_path).name.split(".")[0]
images = Path(args.output_path) / config_name / "images"
meshes = Path(args.output_path) / config_name / "meshes"
images.mkdir(parents=True, exist_ok=True)
meshes.mkdir(parents=True, exist_ok=True)
Path(args.output_path, "argv.txt").write_text("\n".join(sys.argv[1:]), encoding="utf-8")

print("Loading diffusion model ...")
if mode == "missing_weights":
    print("FileNotFoundError: [Errno 2] No such file or directory: 'ckpts/instant_mesh_large.ckpt'", file=sys.stderr)
    sys.exit(1)
print("Loading reconstruction model ...")
print(f"[1/1] Imagining {name} ...")
for step in range(1, args.diffusion_steps + 1):
    percent = round(100 * step / args.diffusion_steps)
    sys.stderr.write(f"\r{percent:3d}%|{'#' * (percent // 10):<10}| {step}/{args.diffusion_steps} [00:00<00:00]")
    sys.stderr.flush()
    if delay:
        time.sleep(delay)
    if mode == "oom" and step == args.diffusion_steps // 2:
        print("\ntorch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB", file=sys.stderr)
        sys.exit(1)
    if mode == "hang":
        time.sleep(3600)
sys.stderr.write("\n")
shutil.copyfile(args.input_path, images / f"{name}.png")
print(f"[1/1] Creating {name} ...")
if mode == "crash":
    print("RuntimeError: unexpected failure in FlexiCubes", file=sys.stderr)
    sys.exit(3)
if mode == "no_output":
    sys.exit(0)

# A 2 x 1 x 0.5 box, tallest along Z as InstantMesh's run.py output is Z-up.
corners = [(x, y, z) for x in (-1.0, 1.0) for y in (-0.25, 0.25) for z in (-0.5, 0.5)]
if mode == "nan":
    corners[0] = (float("nan"), 0.0, 0.0)
quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
lines = [f"v {x} {y} {z} {0.2 + 0.3 * (x > 0):.3f} 0.500 {0.8 - 0.3 * (z > 0):.3f}" for x, y, z in corners]
lines += [f"f {a + 1} {b + 1} {c + 1}\nf {a + 1} {c + 1} {d + 1}" for a, b, c, d in quads]
(meshes / f"{name}.obj").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Mesh saved to {meshes / (name + '.obj')}")
