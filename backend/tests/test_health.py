from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_endpoint():
    """Verify GET /api/v1/health returns 200 OK and expected structure without secrets."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_name"] == "ScholarSwarm AI"
    assert "version" in data
    
    # Verify no sensitive settings leaked
    assert "api_key" not in data
    assert "secret" not in data
    assert "database_url" not in data


def test_root_endpoint():
    """Verify root endpoint responds with basic metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "health_check" in data


def test_cors_headers():
    """Verify CORS headers are returned for allowed frontend origins."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    response = client.options("/api/v1/health", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
