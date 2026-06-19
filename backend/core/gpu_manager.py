"""GPU Resource Manager -- serializes GPU access to prevent VRAM OOM."""

import asyncio
import platform
import subprocess
from contextlib import asynccontextmanager
from typing import Any

import psutil

from core.logging_config import get_logger

log = get_logger(__name__)

_IS_MACOS = platform.system() == "Darwin"
_IS_WINDOWS = platform.system() == "Windows"


def _detect_nvidia() -> dict[str, Any]:
    """Probe NVIDIA GPU via nvidia-smi. Returns partial hardware dict."""
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            parts = proc.stdout.strip().split(",")
            return {
                "gpu_name": parts[0].strip(),
                "vram_total_gb": round(int(parts[1].strip()) / 1024, 1),
                "cuda_available": True,
                "metal_available": False,
                "gpu_type": "nvidia",
            }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return {}


def _detect_apple_silicon() -> dict[str, Any]:
    """Probe Apple Silicon GPU via system_profiler."""
    try:
        proc = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            import json

            data = json.loads(proc.stdout)
            displays = data.get("SPDisplaysDataType", [])
            if displays:
                gpu = displays[0]
                gpu_name = gpu.get("sppci_model", "Apple GPU")
                is_apple_silicon = "apple" in gpu_name.lower() or "m1" in gpu_name.lower() or "m2" in gpu_name.lower() or "m3" in gpu_name.lower() or "m4" in gpu_name.lower()
                return {
                    "gpu_name": gpu_name,
                    "vram_total_gb": None,  # unified memory -- RAM = VRAM
                    "cuda_available": False,
                    "metal_available": True,
                    "gpu_type": "apple_silicon" if is_apple_silicon else "integrated",
                }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return {}


class GPUManager:
    """Singleton that serializes GPU-intensive tasks via an asyncio semaphore.

    On a 6 GB VRAM card (or shared unified memory on Apple Silicon), Ollama,
    Faster Whisper, and ComfyUI cannot share the GPU simultaneously. This
    manager ensures only one GPU consumer runs at a time.
    """

    _instance: "GPUManager | None" = None

    def __new__(cls) -> "GPUManager":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._semaphore = asyncio.Semaphore(1)
            inst._current_task: str | None = None
            inst._queue_length = 0
            cls._instance = inst
        return cls._instance

    @asynccontextmanager
    async def acquire(self, task_type: str, timeout: float = 300):
        """Context manager that acquires exclusive GPU access."""
        self._queue_length += 1
        log.info("gpu_acquire_waiting", task_type=task_type, queue=self._queue_length)
        try:
            acquired = await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
            if not acquired:
                raise TimeoutError(f"GPU lock timeout after {timeout}s for {task_type}")
        except asyncio.TimeoutError:
            self._queue_length -= 1
            raise TimeoutError(f"GPU lock timeout after {timeout}s for {task_type}")

        self._queue_length -= 1
        self._current_task = task_type
        log.info("gpu_acquired", task_type=task_type)
        try:
            yield
        finally:
            self._current_task = None
            self._semaphore.release()
            log.info("gpu_released", task_type=task_type)

    def get_status(self) -> dict[str, Any]:
        """Return current GPU scheduler state."""
        return {
            "state": "busy" if self._current_task else "idle",
            "current_task": self._current_task,
            "queue_length": self._queue_length,
        }

    def detect_hardware(self) -> dict[str, Any]:
        """Detect system RAM, GPU, VRAM -- works on Windows and macOS."""
        mem = psutil.virtual_memory()
        result: dict[str, Any] = {
            "ram_total_gb": round(mem.total / (1024**3), 1),
            "gpu_name": "Unknown",
            "vram_total_gb": 0,
            "cuda_available": False,
            "metal_available": False,
            "gpu_type": None,
        }

        if _IS_MACOS:
            gpu_info = _detect_apple_silicon()
        else:
            gpu_info = _detect_nvidia()

        if gpu_info:
            result["gpu_name"] = gpu_info.get("gpu_name", "Unknown")
            result["vram_total_gb"] = gpu_info.get("vram_total_gb", 0)
            result["cuda_available"] = gpu_info.get("cuda_available", False)
            result["metal_available"] = gpu_info.get("metal_available", False)
            result["gpu_type"] = gpu_info.get("gpu_type")
        elif _IS_MACOS:
            log.debug("apple_gpu_detection_failed")
        else:
            log.debug("nvidia_smi_not_available")

        return result

    def get_recommended_model(self) -> str:
        """Return recommended Ollama model based on system RAM."""
        hw = self.detect_hardware()
        ram = hw["ram_total_gb"]
        if ram >= 32:
            return "qwen3:32b"
        elif ram >= 16:
            return "qwen3:14b"
        else:
            return "qwen3:8b"


gpu_manager = GPUManager()
