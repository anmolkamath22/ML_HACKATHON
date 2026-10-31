"""Download every model and run the real GPU pipeline once on a sample sketch.

Run with the InstantMesh Python (scripts\\warmup_models.cmd does this) after
setup_instantmesh_windows.cmd. It:
  1. runs ControlNet on a sample cube line map (downloads Stable Diffusion 1.5 + ControlNet),
  2. runs InstantMesh on the result (downloads Zero123++, InstantMesh and rembg weights and
     compiles nvdiffrast). If instant-mesh-large runs out of GPU memory it retries with
     instant-mesh-base and saves that choice in backend/.env,
  3. prints the GPU, the stage times and the peak GPU memory.
After this, the app's first generation does not have to download anything.
"""
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "third_party" / "warmup"
PROMPT = ("a cardboard box, single object, centered, full view, product photo, plain white background, "
          "soft studio lighting, highly detailed")
NEGATIVE = ("multiple objects, text, watermark, cropped, out of frame, blurry, low quality, deformed, "
            "pencil sketch, line drawing, cluttered background")


def fail(message: str) -> None:
    print(f"\nWARM-UP FAILED: {message}", flush=True)
    sys.exit(1)


def read_env() -> dict:
    values = {}
    path = ROOT / "backend" / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


class VramSampler(threading.Thread):
    """Samples whole-GPU memory use with nvidia-smi once a second."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.peak: int | None = None
        self.done = threading.Event()
        self.executable = shutil.which("nvidia-smi")

    def run(self) -> None:
        while self.executable and not self.done.is_set():
            try:
                output = subprocess.run([self.executable, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                        capture_output=True, text=True, timeout=5).stdout
                used = sum(int(float(value)) for value in output.split())
                self.peak = max(self.peak or 0, used)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
            self.done.wait(1)


def run_step(title: str, command: list[str], cwd: Path | None = None) -> tuple[int, str, float, int | None]:
    """Run one stage, showing its output live, and return (exit code, output tail, seconds, peak VRAM MB)."""
    print(f"\n=== {title} ===", flush=True)
    sampler = VramSampler()
    sampler.start()
    started = time.perf_counter()
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
    tail = b""
    while chunk := process.stdout.read1(4096):
        sys.stdout.buffer.write(chunk)
        sys.stdout.flush()
        tail = (tail + chunk)[-30000:]
    process.wait()
    sampler.done.set()
    sampler.join(2)
    return process.returncode, tail.decode("utf-8", "replace"), time.perf_counter() - started, sampler.peak


def sample_line_map(path: Path) -> None:
    """A cube drawn as white strokes on black: the input format of the scribble ControlNet."""
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (512, 512), "black")
    draw = ImageDraw.Draw(image)
    front, back = (110, 190, 330, 410), (190, 110, 410, 330)
    draw.rectangle(front, outline="white", width=6)
    draw.rectangle(back, outline="white", width=6)
    for (x1, y1), (x2, y2) in zip([(110, 190), (330, 190), (110, 410), (330, 410)], [(190, 110), (410, 110), (190, 330), (410, 330)]):
        draw.line((x1, y1, x2, y2), fill="white", width=6)
    image.save(path)


def main() -> None:
    env = read_env()
    repo = Path(env.get("INSTANTMESH_REPO") or ROOT / "third_party" / "InstantMesh")
    if not (repo / "run.py").is_file():
        fail(f"InstantMesh was not found at {repo}. Run scripts\\setup_instantmesh_windows.cmd first.")
    try:
        import torch
    except ImportError:
        fail("PyTorch is not installed in this Python. Run this with the InstantMesh environment (scripts\\warmup_models.cmd).")
    if not torch.cuda.is_available():
        fail("PyTorch in the InstantMesh environment cannot see a CUDA GPU. Update the NVIDIA driver and rerun the setup.")
    gpu = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
    print(f"GPU: {gpu} ({vram_gb:.1f} GB), PyTorch {torch.__version__}, CUDA {torch.version.cuda}")
    del torch  # this process keeps no GPU memory; each stage runs in its own process

    OUT.mkdir(parents=True, exist_ok=True)
    control, refined = OUT / "control.png", OUT / "refined.png"
    sample_line_map(control)
    refined.unlink(missing_ok=True)
    code, _, controlnet_seconds, controlnet_peak = run_step(
        "1/2 ControlNet: sketch -> object image (first run downloads about 4 GB)",
        [sys.executable, str(ROOT / "backend" / "inference_scripts" / "controlnet_refine.py"),
         "--control", str(control), "--output", str(refined), "--prompt", PROMPT, "--negative-prompt", NEGATIVE,
         "--steps", env.get("CONTROLNET_STEPS") or "20", "--memory", env.get("CONTROLNET_MEMORY") or "auto",
         "--base-model", env.get("CONTROLNET_BASE_MODEL") or "stable-diffusion-v1-5/stable-diffusion-v1-5",
         "--controlnet-model", env.get("CONTROLNET_MODEL") or "lllyasviel/control_v11p_sd15_scribble"])
    controlnet_ok = code == 0 and refined.is_file()
    if not controlnet_ok:
        print("\nControlNet failed (see above). The app still works without it: jobs fall back to the sketch cutout.")
        from PIL import ImageOps, Image
        ImageOps.invert(Image.open(control).convert("RGB")).save(refined)  # black-on-white sketch for InstantMesh

    def instantmesh(config: str):
        shutil.rmtree(OUT / "instantmesh", ignore_errors=True)
        return run_step(f"2/2 InstantMesh ({Path(config).stem}): image -> 3D mesh (first run downloads about 6 GB)",
                        [sys.executable, "run.py", config, str(refined), "--output_path", str(OUT / "instantmesh"),
                         "--diffusion_steps", "75", "--seed", "42"], cwd=repo)

    config = env.get("INSTANTMESH_CONFIG") or "configs/instant-mesh-large.yaml"
    code, log, mesh_seconds, mesh_peak = instantmesh(config)
    if code != 0 and "out of memory" in log.lower() and "large" in config:
        print("\nThe large model ran out of GPU memory. Retrying with instant-mesh-base ...")
        config = "configs/instant-mesh-base.yaml"
        code, log, mesh_seconds, mesh_peak = instantmesh(config)
        if code == 0:
            subprocess.run([sys.executable, str(ROOT / "scripts" / "configure_env.py"), f"INSTANTMESH_CONFIG={config}"], check=False)
    meshes = sorted((OUT / "instantmesh").glob("*/meshes/*.obj"))
    if code != 0 or not meshes:
        fail("InstantMesh did not produce a mesh. Read the output above and docs/TROUBLESHOOTING.md.")

    peaks = [value for value in (controlnet_peak, mesh_peak) if value]
    print("\n" + "=" * 72)
    if controlnet_ok:
        print("Warm-up finished: all models are downloaded and the GPU pipeline works.")
    else:
        print("Warm-up finished with a problem: InstantMesh works, but ControlNet failed (see its output above).")
        print("The app still runs (jobs fall back to the sketch), but fix ControlNet before recording the demo.")
    print(f"  GPU:               {gpu} ({vram_gb:.1f} GB)")
    print(f"  ControlNet:        {'OK' if controlnet_ok else 'FAILED (app falls back to the sketch)'}, {controlnet_seconds:.0f} s")
    print(f"  InstantMesh:       OK with {Path(config).stem}, {mesh_seconds:.0f} s")
    print(f"  Peak GPU memory:   {max(peaks) if peaks else 'unknown'} MB (whole GPU)")
    print(f"  Test mesh:         {meshes[0]}")
    print("These times include downloads and compilation on the first run. For the README, use the")
    print("timings in the app's result panel after a normal generation, or run this script again.")
    print("Start the app with:  scripts\\serve.cmd --public")


if __name__ == "__main__":
    main()
