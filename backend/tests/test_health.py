def test_root(anon_client):
    response = anon_client.get("/")
    assert response.status_code == 200
    assert "running" in response.json()["message"]


def test_healthz_is_public(anon_client):
    response = anon_client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_status_requires_login(anon_client):
    assert anon_client.get("/status").status_code == 401


def test_status_never_leaks_secrets(client):
    response = client.get("/status")
    assert response.status_code == 200
    assert "mongodb://" not in response.text
    assert "unused-in-tests" not in response.text
