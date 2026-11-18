"""SA-19 : API catalogue — lecture publique, droits par établissement, corrections manuelles."""
import pytest

from tests.conftest import ADMIN, login, user_with_role

API = "/api/v1"


def program_body(code="ISB-TEST", institution="ISB", amount="100.00", **extra):
    return {
        "code": code, "institution_code": institution, "level": "licence", "name": "Test", "duration_years": 3,
        "source_url": "https://isb.tn/test/",
        "fees": [{"academic_year": "2026-2027", "fee_type": "inscription", "amount": amount, "is_official": True}],
        **extra,
    }


def test_institutions_are_public(client):
    r = client.get(f"{API}/institutions")
    assert r.status_code == 200 and {i["code"] for i in r.json()} == {"IIT", "ISB"}


def test_programs_filters(client):
    licences = client.get(f"{API}/programs", params={"institution": "iit", "level": "licence"}).json()
    assert [p["code"] for p in licences] == ["IIT-LIC-INFO"]
    assert {p["code"] for p in client.get(f"{API}/programs", params={"institution": "IIT"}).json()} == {
        "IIT-PREPA", "IIT-LIC-INFO", "IIT-ING-GI"
    }
    assert [p["code"] for p in client.get(f"{API}/programs", params={"level": "prepa"}).json()] == ["IIT-PREPA"]
    assert client.get(f"{API}/programs", params={"institution": "ISB"}).json() == []
    assert client.get(f"{API}/programs", params={"level": "doctorat"}).status_code == 422


def test_program_detail_and_404(client):
    detail = client.get(f"{API}/programs/IIT-ING-GI").json()
    assert detail["institution"]["code"] == "IIT" and "requirements" in detail and "fees" in detail
    r = client.get(f"{API}/programs/INCONNU")
    assert r.status_code == 404 and r.json()["code"] == "PROGRAM_NOT_FOUND"


def test_write_requires_auth_and_editor_role(client):
    assert client.post(f"{API}/programs", json=program_body()).status_code == 401
    candidate = user_with_role(client, "cand@test.tn", "candidate")
    assert client.post(f"{API}/programs", json=program_body(), headers=candidate).status_code == 403
    direction = user_with_role(client, "dir@test.tn", "direction")
    assert client.post(f"{API}/programs", json=program_body(), headers=direction).status_code == 403


def test_iit_manager_only_manages_iit(client):
    resp_iit = user_with_role(client, "iit@test.tn", "academic_iit")
    r = client.post(f"{API}/programs", json=program_body(), headers=resp_iit)
    assert r.status_code == 403 and r.json()["code"] == "OUT_OF_SCOPE"
    r = client.post(f"{API}/programs", json=program_body("IIT-TEST", "IIT"), headers=resp_iit)
    assert r.status_code == 201
    # il ne peut pas non plus « déplacer » une formation IIT vers l'ISB
    assert client.put(f"{API}/programs/IIT-TEST", json=program_body("IIT-TEST", "ISB"), headers=resp_iit).status_code == 403


def test_isb_manager_only_manages_isb(client):
    resp_isb = user_with_role(client, "isb@test.tn", "academic_isb")
    assert client.put(f"{API}/programs/IIT-LIC-INFO", json=program_body("IIT-LIC-INFO", "IIT"),
                      headers=resp_isb).status_code == 403
    assert client.post(f"{API}/programs", json=program_body(), headers=resp_isb).status_code == 201


def test_admin_creates_manual_locked_program(client):
    admin = login(client, *ADMIN)
    r = client.post(f"{API}/programs", json=program_body(), headers=admin)
    assert r.status_code == 201
    assert r.json()["data_source"] == "manual" and r.json()["fees"][0]["is_official"] is True
    r = client.post(f"{API}/programs", json=program_body(), headers=admin)
    assert r.status_code == 409 and r.json()["code"] == "PROGRAM_CODE_ALREADY_USED"


def test_unknown_institution_is_400(client):
    r = client.post(f"{API}/programs", json=program_body("XYZ-1", "XYZ"), headers=login(client, *ADMIN))
    assert r.status_code == 400 and r.json()["code"] == "UNKNOWN_INSTITUTION"


def test_update_replaces_fees_without_unique_violation(client):
    admin = login(client, *ADMIN)
    client.post(f"{API}/programs", json=program_body("ISB-UPD"), headers=admin)
    r = client.put(f"{API}/programs/ISB-UPD", json=program_body("ISB-UPD", amount="120.00"), headers=admin)
    assert r.status_code == 200 and [f["amount"] for f in r.json()["fees"]] == ["120.00"]
    assert client.put(f"{API}/programs/NOPE", json=program_body("NOPE"), headers=admin).status_code == 404


@pytest.mark.parametrize("missing", ["name", "level", "institution_code"])
def test_missing_field_is_422(client, missing):
    body = program_body()
    del body[missing]
    r = client.post(f"{API}/programs", json=body, headers=login(client, *ADMIN))
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
