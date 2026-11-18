"""SA-35 : intégration du LLM et dialogue multi-tours (visiteur sans compte)."""
import pytest

from app.api.routes_chat import official_context
from app.db.models import Message, Program
from app.llm.client import SYSTEM_PROMPT, LLMClient, LLMUnavailable, get_llm
from app.llm.language import detect_language
from app.main import app

API = "/api/v1"


class RecordingLLM(LLMClient):
    """Faux LLM qui garde les messages reçus pour vérifier l'historique et le contexte."""

    def __init__(self):
        super().__init__("fake")
        self.calls: list[list[dict]] = []

    def chat(self, messages):
        self.calls.append(messages)
        return super().chat(messages)


@pytest.fixture()
def recording_llm():
    llm = RecordingLLM()
    app.dependency_overrides[get_llm] = lambda: llm
    yield llm
    app.dependency_overrides.pop(get_llm, None)


def test_two_turn_conversation_keeps_history(client, session_id, recording_llm):
    h = {"X-Session-Id": session_id}
    r1 = client.post(f"{API}/chat/messages", json={"message": "Bonjour, je veux faire informatique"}, headers=h)
    assert r1.status_code == 200 and r1.json()["language"] == "fr"
    conv = r1.json()["conversation_id"]
    r2 = client.post(f"{API}/chat/messages", json={"message": "et la prépa ?", "conversation_id": conv}, headers=h)
    assert r2.status_code == 200 and "tour 2" in r2.json()["reply"]
    second_call = recording_llm.calls[1]
    assert [m["role"] for m in second_call] == ["system", "user", "assistant", "user"]
    assert second_call[1]["content"] == "Bonjour, je veux faire informatique"
    msgs = client.get(f"{API}/chat/conversations/{conv}/messages", headers=h).json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert [c["id"] for c in client.get(f"{API}/chat/conversations", headers=h).json()] == [conv]


def test_history_window_is_limited(client, session_id, recording_llm, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "chat_history_window", 2)
    h = {"X-Session-Id": session_id}
    conv = client.post(f"{API}/chat/messages", json={"message": "m1"}, headers=h).json()["conversation_id"]
    for text in ("m2", "m3"):
        client.post(f"{API}/chat/messages", json={"message": text, "conversation_id": conv}, headers=h)
    assert len(recording_llm.calls[-1]) == 1 + 2 + 1  # system + 2 derniers messages + nouveau message


def test_system_prompt_and_official_context(client, session_id, recording_llm):
    client.post(f"{API}/chat/messages", json={"message": "chnowa el far9 bin prepa w licence ?"},
                headers={"X-Session-Id": session_id})
    system = recording_llm.calls[0][0]["content"]
    assert system.startswith(SYSTEM_PROMPT)
    assert "Arabizi" in system and "CONTEXTE OFFICIEL" in system and "IIT-" not in system
    assert "Licence en informatique" in system


def test_official_context_shows_duration_only_if_known(db):
    prog = db.query(Program).filter_by(code="IIT-LIC-INFO").one()
    prog.duration_years = None
    prog.source_url = "https://iit.tn/licence-info/"
    db.commit()
    line = next(l for l in official_context(db).splitlines() if "Licence en informatique" in l)
    assert " ans" not in line and "source : https://iit.tn/licence-info/" in line


def test_system_prompt_rules():
    for rule in ("5 phrases", "une seule question", "N'invente jamais", "indicatifs", "aucune décision officielle"):
        assert rule in SYSTEM_PROMPT


def test_model_and_latency_are_recorded(client, session_id, db):
    client.post(f"{API}/chat/messages", json={"message": "salut"}, headers={"X-Session-Id": session_id})
    answer = db.query(Message).filter_by(role="assistant").one()
    assert answer.model == "fake" and answer.latency_ms is not None and answer.language == "fr"


def test_session_is_required(client):
    r = client.post(f"{API}/chat/messages", json={"message": "salut"})
    assert r.status_code == 400 and r.json()["code"] == "SESSION_ID_MISSING"
    assert client.get(f"{API}/chat/conversations").status_code == 400


def test_sessions_are_isolated(client, session_id):
    conv = client.post(
        f"{API}/chat/messages", json={"message": "bonjour"}, headers={"X-Session-Id": session_id}
    ).json()["conversation_id"]
    other = {"X-Session-Id": client.post(f"{API}/sessions").json()["session_id"]}
    assert client.get(f"{API}/chat/conversations/{conv}/messages", headers=other).status_code == 404
    assert client.get(f"{API}/chat/conversations", headers=other).json() == []
    r = client.post(f"{API}/chat/messages", json={"message": "x", "conversation_id": conv}, headers=other)
    assert r.status_code == 404 and r.json()["code"] == "CONVERSATION_NOT_FOUND"


def test_llm_unavailable_returns_503_and_saves_nothing(client, session_id, db):
    class DownLLM(LLMClient):
        def chat(self, messages):
            raise LLMUnavailable("ConnectError")

    app.dependency_overrides[get_llm] = lambda: DownLLM("openai")
    try:
        r = client.post(f"{API}/chat/messages", json={"message": "salut"}, headers={"X-Session-Id": session_id})
    finally:
        app.dependency_overrides.pop(get_llm, None)
    assert r.status_code == 503 and r.json()["code"] == "LLM_UNAVAILABLE"
    assert db.query(Message).count() == 0


def test_real_client_wraps_network_errors(monkeypatch):
    import httpx

    def boom(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(LLMUnavailable):
        LLMClient("openai").chat([{"role": "user", "content": "salut"}])


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Quelles sont les conditions d'accès à la licence ?", "fr"),
        ("chnowa el far9 bin prepa w licence ?", "arabizi"),
        ("نحب نقرا informatique، شنوة الفرق؟", "tn"),
        ("ما هي شروط القبول في الهندسة؟", "ar"),
    ],
)
def test_language_detection(text, expected):
    assert detect_language(text) == expected
