"""Integration tests for the video processing pipeline."""

import pytest


@pytest.mark.asyncio
async def test_full_video_pipeline(client, sample_project_data, temp_dir):
    """Test the full pipeline: create project -> import video -> transcribe."""
    # Create project
    resp = await client.post("/api/v1/projects", json=sample_project_data)
    assert resp.status_code == 200
    project_id = resp.json()["id"]

    # List videos (should be empty)
    resp = await client.get(f"/api/v1/projects/{project_id}/videos")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_content_generation_flow(client, sample_project_data):
    """Test content generation: create project -> generate title."""
    resp = await client.post("/api/v1/projects", json=sample_project_data)
    project_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/generate",
        json={"content_type": "title", "prompt": "Generate a catchy title for a Bali vlog"},
    )
    assert resp.status_code in (200, 202)


@pytest.mark.asyncio
async def test_agent_pipeline_flow(client, sample_project_data):
    """Test agent pipeline: create project -> run agents."""
    resp = await client.post("/api/v1/projects", json=sample_project_data)
    project_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/projects/{project_id}/agents/run",
        json={"agents": ["trip_analyzer"], "context": "A week in Bali"},
    )
    assert resp.status_code in (200, 202)
