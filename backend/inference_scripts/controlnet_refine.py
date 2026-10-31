"""Sketch -> object image with Stable Diffusion 1.5 + ControlNet (scribble).

Runs in the InstantMesh Python environment, which already provides torch and
diffusers. It is a separate process so its VRAM is released before InstantMesh
starts. Prints "ControlNet step i/N" lines for progress and a final JSON line.

The control image must be white strokes on a black background, as the
scribble ControlNet expects.
"""
import argparse
import inspect
import json
import sys


def load(cls, name: str, torch, **kwargs):
    """Prefer the smaller fp16 weights; fall back to the default files."""
    try:
        return cls.from_pretrained(name, torch_dtype=torch.float16, variant="fp16", **kwargs)
    except Exception:  # noqa: BLE001 - the fp16 variant is optional on the Hub
        return cls.from_pretrained(name, torch_dtype=torch.float16, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--guidance", type=float, default=7.5)
    parser.add_argument("--conditioning-scale", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--base-model", default="stable-diffusion-v1-5/stable-diffusion-v1-5")
    parser.add_argument("--controlnet-model", default="lllyasviel/control_v11p_sd15_scribble")
    parser.add_argument("--memory", choices=["auto", "full", "offload"], default="auto")
    args = parser.parse_args()

    import torch
    from diffusers import ControlNetModel, StableDiffusionControlNetPipeline, UniPCMultistepScheduler
    from PIL import Image

    if not torch.cuda.is_available():
        print("RuntimeError: no CUDA GPU is available for ControlNet", file=sys.stderr)
        sys.exit(2)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
    memory = args.memory if args.memory != "auto" else ("full" if vram_gb >= 8 else "offload")

    print("Loading ControlNet models ...", flush=True)
    controlnet = load(ControlNetModel, args.controlnet_model, torch)
    pipe = load(StableDiffusionControlNetPipeline, args.base_model, torch, controlnet=controlnet,
                safety_checker=None, requires_safety_checker=False)
    pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config)
    if memory == "offload":
        # Keeps only the active sub-model on the GPU: fits 4 GB cards at some speed cost.
        try:
            pipe.enable_model_cpu_offload()
        except Exception as exc:  # noqa: BLE001 - needs accelerate; fall back to plain GPU use
            print(f"CPU offload unavailable ({exc}); loading the whole pipeline on the GPU.", flush=True)
            memory = "full"
            pipe.to("cuda")
    else:
        pipe.to("cuda")
    pipe.enable_attention_slicing()
    pipe.set_progress_bar_config(disable=True)

    def report(step: int) -> None:
        print(f"ControlNet step {step}/{args.steps}", flush=True)

    # diffusers >= 0.22 uses callback_on_step_end; older releases use callback/callback_steps.
    params = inspect.signature(pipe.__call__).parameters
    if "callback_on_step_end" in params:
        def on_step_end(_pipe, index, _timestep, callback_kwargs):
            report(index + 1)
            return callback_kwargs
        callbacks = {"callback_on_step_end": on_step_end}
    else:
        callbacks = {"callback": lambda index, _timestep, _latents: report(index + 1), "callback_steps": 1}

    control = Image.open(args.control).convert("RGB")
    print("Generating the object image ...", flush=True)
    image = pipe(args.prompt, image=control, negative_prompt=args.negative_prompt or None,
                 num_inference_steps=args.steps, guidance_scale=args.guidance,
                 controlnet_conditioning_scale=args.conditioning_scale,
                 generator=torch.Generator(device="cpu").manual_seed(args.seed), **callbacks).images[0]
    image.save(args.output)
    print(json.dumps({"output": args.output, "memory_mode": memory, "device": torch.cuda.get_device_name(0),
                      "vram_gb": round(vram_gb, 1), "peak_allocated_mb": torch.cuda.max_memory_allocated() // (1024 * 1024)}))


if __name__ == "__main__":
    main()
