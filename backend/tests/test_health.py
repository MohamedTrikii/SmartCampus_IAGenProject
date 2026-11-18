"""SA-6 : socle FastAPI — santé, préfixe /api/v1, format d'erreur unique, CORS."""
API = "/api/v1"


def test_health(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_unknown_route_uses_error_format(client):
    r = client.get(f"{API}/route-inexistante")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found", "code": "NOT_FOUND"}


def test_validation_error_format(client):
    r = client.post(f"{API}/auth/register", json={"email": "pas-un-email", "password": "court"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "VALIDATION_ERROR"
    fields = {e["field"] for e in body["errors"]}
    assert {"body.email", "body.password", "body.full_name"} <= fields


def test_cors_allows_frontend(client):
    r = client.options(
        f"{API}/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_openapi_docs_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "SmartCampus AI"
