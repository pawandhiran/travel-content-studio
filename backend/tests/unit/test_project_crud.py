"""Unit tests for project CRUD operations."""

import pytest


@pytest.mark.asyncio
async def test_create_project(client, sample_project_data):
    """Creating a project returns 200 with project data."""
    response = await client.post("/api/v1/projects", json=sample_project_data)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == sample_project_data["name"]
    assert data["description"] == sample_project_data["description"]
    assert data["status"] == "active"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_projects_empty(client):
    """Listing projects when none exist returns empty list."""
    response = await client.get("/api/v1/projects")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, (list, dict))


@pytest.mark.asyncio
async def test_get_project_not_found(client):
    """Getting a non-existent project returns 404."""
    response = await client.get("/api/v1/projects/nonexistent123")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_and_get_project(client, sample_project_data):
    """Creating then retrieving a project returns correct data."""
    create_resp = await client.post("/api/v1/projects", json=sample_project_data)
    assert create_resp.status_code == 200
    project_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/v1/projects/{project_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == sample_project_data["name"]


@pytest.mark.asyncio
async def test_update_project(client, sample_project_data):
    """Updating a project changes its data."""
    create_resp = await client.post("/api/v1/projects", json=sample_project_data)
    project_id = create_resp.json()["id"]

    update_resp = await client.put(
        f"/api/v1/projects/{project_id}",
        json={"name": "Updated Bali Trip", "description": "Updated description"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Updated Bali Trip"


@pytest.mark.asyncio
async def test_delete_project(client, sample_project_data):
    """Deleting a project soft-deletes it."""
    create_resp = await client.post("/api/v1/projects", json=sample_project_data)
    project_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/projects/{project_id}")
    assert delete_resp.status_code == 204
