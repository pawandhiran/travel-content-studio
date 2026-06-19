"""Unit tests for GPU Resource Manager."""

import asyncio

import pytest

from core.gpu_manager import GPUManager


@pytest.mark.asyncio
async def test_gpu_manager_singleton():
    """GPUManager should be reusable."""
    manager = GPUManager()
    status = manager.get_status()
    assert status["state"] == "idle"
    assert status["current_task"] is None


@pytest.mark.asyncio
async def test_gpu_acquire_release():
    """Acquiring and releasing GPU lock works."""
    manager = GPUManager()

    async with manager.acquire("test_task"):
        status = manager.get_status()
        assert status["state"] == "busy"
        assert status["current_task"] == "test_task"

    status = manager.get_status()
    assert status["state"] == "idle"


@pytest.mark.asyncio
async def test_gpu_serialization():
    """Two GPU tasks cannot run simultaneously."""
    manager = GPUManager()
    order = []

    async def task(name: str, delay: float):
        async with manager.acquire(name):
            order.append(f"{name}_start")
            await asyncio.sleep(delay)
            order.append(f"{name}_end")

    await asyncio.gather(task("first", 0.1), task("second", 0.1))

    assert order[0] == "first_start"
    assert order[1] == "first_end"
    assert order[2] == "second_start"
    assert order[3] == "second_end"


@pytest.mark.asyncio
async def test_detect_hardware():
    """Hardware detection returns a dict with expected keys."""
    manager = GPUManager()
    hw = manager.detect_hardware()
    assert "ram_total_gb" in hw
    assert "gpu_name" in hw
    assert "cuda_available" in hw
    assert hw["ram_total_gb"] > 0


@pytest.mark.asyncio
async def test_recommended_model():
    """Model recommendation returns a valid model name."""
    manager = GPUManager()
    model = manager.get_recommended_model()
    assert model in ["qwen3:8b", "qwen3:14b", "qwen3:32b"]
