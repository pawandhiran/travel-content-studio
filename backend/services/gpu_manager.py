"""GPU and hardware detection utilities -- cross-platform (Windows + macOS)."""

import platform
import subprocess

from models.schemas import HardwareInfoResponse


def detect_hardware() -> HardwareInfoResponse:
    """Detect system hardware: CPU, RAM, GPU, VRAM, disk."""
    import psutil

    cpu = platform.processor() or platform.machine()
    cpu_cores = psutil.cpu_count(logical=True) or 1
    mem = psutil.virtual_memory()

    root = "/" if platform.system() != "Windows" else "C:\\"
    disk = psutil.disk_usage(root)

    gpu_name = None
    gpu_vram = None
    gpu_type = None
    cuda_available = False
    metal_available = False

    if platform.system() == "Darwin":
        gpu_name, gpu_type, metal_available = _detect_macos_gpu()
    else:
        gpu_name, gpu_vram, cuda_available = _detect_nvidia_gpu()
        if gpu_name:
            gpu_type = "nvidia"

    return HardwareInfoResponse(
        cpu=cpu,
        cpu_cores=cpu_cores,
        ram_total_gb=round(mem.total / (1024**3), 1),
        ram_available_gb=round(mem.available / (1024**3), 1),
        gpu=gpu_name,
        gpu_vram_gb=gpu_vram,
        gpu_type=gpu_type,
        cuda_available=cuda_available,
        metal_available=metal_available,
        disk_total_gb=round(disk.total / (1024**3), 1),
        disk_free_gb=round(disk.free / (1024**3), 1),
    )


def _detect_nvidia_gpu() -> tuple:
    """Returns (gpu_name, vram_gb, cuda_available)."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(",")
            return parts[0].strip(), round(int(parts[1].strip()) / 1024, 1), True
    except Exception:
        pass
    return None, None, False


def _detect_macos_gpu() -> tuple:
    """Returns (gpu_name, gpu_type, metal_available)."""
    try:
        import json

        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            displays = data.get("SPDisplaysDataType", [])
            if displays:
                gpu = displays[0]
                name = gpu.get("sppci_model", "Apple GPU")
                is_apple = any(
                    chip in name.lower()
                    for chip in ("apple", "m1", "m2", "m3", "m4")
                )
                gpu_type = "apple_silicon" if is_apple else "integrated"
                return name, gpu_type, True
    except Exception:
        pass
    return None, None, False
