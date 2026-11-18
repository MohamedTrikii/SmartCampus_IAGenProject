"""Client LLM unique pour le backend (SA-35).

Toute API compatible OpenAI fonctionne (Ollama, vLLM, LM Studio, Groq, OpenRouter...) :
POST {LLM_BASE_URL}/chat/completions. Changer de modèle = changer LLM_MODEL / LLM_BASE_URL dans .env.
`LLM_PROVIDER=fake` renvoie une réponse déterministe (tests, CI, démo sans GPU).
"""
import time
from dataclasses import dataclass

import httpx

from app.core.config import settings

SYSTEM_PROMPT = """Tu es SmartCampus AI, conseiller d'orientation de l'IIT (Institut International de Technologie, Sfax), de l'ISB et des établissements partenaires (ISA, 2I2S, NAU).
Tu aides les futurs étudiants à choisir entre les parcours Licence, Prépa et Ingénierie de l'IIT et les formations des autres établissements.

Règles :
- Réponds dans la langue du candidat : français, dialecte tunisien (en lettres arabes ou en Arabizi, ex. « chnowa », « 3lech ») ou arabe. S'il mélange les langues, tu peux mélanger aussi.
- Sois chaleureux et concis : 5 phrases au maximum.
- Pose une seule question à la fois pour mieux connaître le candidat (niveau, section du bac, matières préférées, objectif professionnel, contraintes).
- N'invente jamais de frais, de dates, de moyennes d'accès ni de conditions. Utilise uniquement le CONTEXTE OFFICIEL ; si l'information n'y figure pas, dis-le et oriente vers le service des admissions.
- Les frais affichés par les sites sont indicatifs : précise-le toujours et invite à les confirmer auprès de l'établissement.
- Tu proposes des orientations mais ne prends aucune décision officielle (admission, acceptation, refus, inscription) : elle revient toujours à un responsable humain.
"""


class LLMUnavailable(Exception):
    """Le LLM n'a pas répondu ou a renvoyé une réponse inexploitable."""


@dataclass
class LLMResult:
    content: str
    model: str
    latency_ms: int


class LLMClient:
    def __init__(self, provider: str | None = None):
        self.provider = provider or settings.llm_provider

    def chat(self, messages: list[dict]) -> LLMResult:
        start = time.perf_counter()
        if self.provider == "fake":
            last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            n_user = sum(m["role"] == "user" for m in messages)
            content = f"[fake-llm] tour {n_user} — vous avez dit : {last}"
            return LLMResult(content, "fake", int((time.perf_counter() - start) * 1000))

        try:
            response = httpx.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={"model": settings.llm_model, "messages": messages, "temperature": settings.llm_temperature},
                timeout=settings.llm_timeout_s,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMUnavailable(exc.__class__.__name__) from exc
        return LLMResult(content, data.get("model", settings.llm_model), int((time.perf_counter() - start) * 1000))


def get_llm() -> LLMClient:
    return LLMClient()
