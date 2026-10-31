"""Report the GPU that the inference environment's PyTorch can use, as one JSON line.

Run with the InstantMesh Python. Works for any GPU PyTorch knows about: NVIDIA
(CUDA), AMD (ROCm builds report through torch.cuda with torch.version.hip set)
and Apple (MPS). Also checks that this PyTorch build ships kernels for the GPU's
architecture, which catches e.g. a brand-new GPU paired with an old PyTorch.
"""
import json

info: dict = {}
try:
    import torch

    info["torch"] = torch.__version__
    info["cuda_version"] = torch.version.cuda
    info["hip_version"] = getattr(torch.version, "hip", None)
    info["cuda_available"] = torch.cuda.is_available()
    info["mps_available"] = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    if info["cuda_available"]:
        props = torch.cuda.get_device_properties(0)
        info.update(name=props.name, memory_total_mb=props.total_memory // (1024 * 1024),
                    device_count=torch.cuda.device_count(), capability=f"{props.major}.{props.minor}")
        arch_list = torch.cuda.get_arch_list()
        info["arch_list"] = arch_list
        if not info["hip_version"] and arch_list:
            device = (props.major, props.minor)
            built = [(arch.split("_")[0], divmod(int(arch.split("_")[1]), 10)) for arch in arch_list
                     if arch.count("_") == 1 and arch.split("_")[1].isdigit()]
            # sm_XY binaries run on the same major with an equal or newer minor (sm_86 on an
            # sm_89 RTX 40xx); compute_XY PTX can be JIT-compiled for any newer GPU.
            info["arch_supported"] = any((kind == "sm" and arch[0] == device[0] and arch[1] <= device[1])
                                         or (kind == "compute" and arch <= device) for kind, arch in built)
except Exception as exc:  # noqa: BLE001 - report every failure to the backend
    info["error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(info))
