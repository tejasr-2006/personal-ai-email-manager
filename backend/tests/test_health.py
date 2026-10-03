def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "running" in response.json()["message"]


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_status_never_leaks_secrets(client):
    body = client.get("/status").text
    assert "mongodb://" not in body
    assert "unused-in-tests" not in body
