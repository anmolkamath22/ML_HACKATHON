"""TEST DOUBLE for inference_scripts/gpu_probe.py. FAKE_GPU selects the reported hardware."""
import json
import os

profiles = {
    "cuda": {"torch": "2.1.0", "cuda_available": True, "name": "NVIDIA GeForce RTX 4050 Laptop GPU", "memory_total_mb": 6141,
             "capability": "8.9", "arch_supported": True, "hip_version": None},
    "none": {"torch": "2.1.0", "cuda_available": False, "hip_version": None},
    "rocm": {"torch": "2.1.0", "cuda_available": True, "name": "AMD Radeon RX 7600", "memory_total_mb": 8176, "hip_version": "5.6"},
    "mps": {"torch": "2.1.0", "cuda_available": False, "mps_available": True},
    "old_torch": {"torch": "2.1.0", "cuda_available": True, "name": "NVIDIA GeForce RTX 5050 Laptop GPU", "memory_total_mb": 8151,
                  "capability": "12.0", "arch_supported": False, "hip_version": None},
    "broken": {"error": "ImportError: libcudart.so.12: cannot open shared object file"},
}
print(json.dumps(profiles[os.environ.get("FAKE_GPU", "cuda")]))
