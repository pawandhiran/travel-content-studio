"""Unit tests for system API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Health endpoint returns 200."""
    response = await client.get("/api/v1/system/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_hardware_endpoint(client):
    """Hardware endpoint returns system info."""
    response = await client.get("/api/v1/system/hardware")
    assert response.status_code == 200
    data = response.json()
    assert "ram_total_gb" in data


@pytest.mark.asyncio
async def test_models_endpoint(client):
    """Models endpoint returns model info."""
    response = await client.get("/api/v1/system/models")
    assert response.status_code == 200
    data = response.json()
    assert "recommended_model" in data
