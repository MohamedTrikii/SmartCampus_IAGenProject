"""Banc d'évaluation des LLM candidats — SA-31.

Pour chaque modèle et chaque question du jeu (FR / tunisien en arabe / Arabizi) :
  1. Compréhension : le modèle classe l'intention et la langue (sortie JSON) → accuracy.
  2. Génération   : le modèle répond comme l'assistant SmartCampus →
       - cohérence de langue (répond-il dans la langue du candidat ?)
       - hallucination de frais (invente-t-il un montant alors qu'aucun n'est fourni ?)
       - latence moyenne / p95
  3. Export d'une grille CSV pour la notation humaine (pertinence, naturel du dialecte, 1 à 5).

Usage :
  python evaluate.py --models qwen2.5:7b-instruct llama3.1:8b gemma2:9b
  python evaluate.py --models fake            # test du script sans LLM
  python evaluate.py --models mistral:7b --skip-done --machine "Kaggle T4"   # un modèle à la fois, reprise possible
  python evaluate.py --summary-only           # reconstruit summary.md à partir des résultats déjà présents
Chaque modèle écrit results/<modele>_summary.json ; summary.md regroupe tous les modèles du dossier.
Variables : LLM_BASE_URL (défaut Ollama http://localhost:11434/v1), LLM_API_KEY.
"""
import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
from app.llm.client import SYSTEM_PROMPT  # noqa: E402
from app.llm.language import detect_language  # noqa: E402

INTENTS = [
    "info_programme", "conditions_acces", "frais", "comparaison", "orientation_perso",
    "preinscription", "rendez_vous", "salutation", "hors_sujet",
]
LANGS = ["fr", "tn", "arabizi"]

CLASSIFY_PROMPT = f"""Tu analyses le message d'un futur étudiant tunisien qui contacte un service d'orientation universitaire.
Réponds UNIQUEMENT avec un objet JSON sur une ligne : {{"intent": "...", "language": "..."}}
- intent parmi : {", ".join(INTENTS)}
- language parmi : fr (français), tn (dialecte tunisien écrit en lettres arabes), arabizi (tunisien écrit en lettres latines avec chiffres 3,7,9,5)
"""

CONTEXT = """CONTEXTE OFFICIEL (formations disponibles) :
- [IIT] Cycle préparatoire intégré (prepa, 2 ans)
- [IIT] Licence en informatique (licence, 3 ans)
- [IIT] Cycle ingénieur Génie Informatique (ingenieur, 3 ans)
Aucun frais de scolarité n'est fourni dans ce contexte."""

FEE_PATTERN = re.compile(r"\d[\d\s.,]*\s*(dt|tnd|dinars?|د\.?ت|دينار|€|eur|euros?)", re.IGNORECASE)


def lang_family(lang: str) -> str:
    return "fr" if lang == "fr" else "dialect"  # tn, arabizi, ar comptent comme réponse "en dialecte/arabe"


def call(model: str, messages: list[dict], base_url: str, api_key: str, json_mode=False) -> tuple[str, float]:
    start = time.perf_counter()
    if model == "fake":
        user = messages[-1]["content"]
        out = json.dumps({"intent": "comparaison", "language": detect_language(user)}) if json_mode else user
        return out, time.perf_counter() - start
    body = {"model": model, "messages": messages, "temperature": 0.0 if json_mode else 0.3}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = httpx.post(f"{base_url.rstrip('/')}/chat/completions", json=body,
                   headers={"Authorization": f"Bearer {api_key}"}, timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip(), time.perf_counter() - start


def parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        return json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}


def evaluate(model: str, items: list[dict], base_url: str, api_key: str, out_dir: Path) -> dict:
    rows = []
    for item in items:
        q = item["question"]
        error = None
        try:
            raw_cls, _ = call(model, [{"role": "system", "content": CLASSIFY_PROMPT}, {"role": "user", "content": q}],
                              base_url, api_key, json_mode=True)
            pred = parse_json(raw_cls)
            answer, latency = call(model, [{"role": "system", "content": f"{SYSTEM_PROMPT}\n{CONTEXT}"},
                                           {"role": "user", "content": q}], base_url, api_key)
        except (httpx.HTTPError, KeyError, ValueError) as exc:  # un échec compte comme une erreur, sans arrêter le banc
            pred, answer, latency, error = {}, "", 180.0, f"{exc.__class__.__name__}: {exc}"
        rows.append({
            **item,
            "pred_intent": pred.get("intent"),
            "pred_language": pred.get("language"),
            "intent_ok": pred.get("intent") == item["intent"],
            "langid_ok": pred.get("language") == item["language"],
            "reply": answer,
            "reply_language": detect_language(answer),
            "lang_consistent": bool(answer) and lang_family(detect_language(answer)) == lang_family(item["language"]),
            "lang_exact": bool(answer) and detect_language(answer) == item["language"],
            "fee_hallucination": item["intent"] == "frais" and bool(FEE_PATTERN.search(answer)),
            "latency_s": round(latency, 2),
            "error": error,
        })
        print(f"  {item['id']} {item['language']:8} intent={'✓' if rows[-1]['intent_ok'] else '✗'} "
              f"lang={'✓' if rows[-1]['lang_consistent'] else '✗'} {latency:.1f}s")

    safe = re.sub(r"[^\w.-]", "_", model)
    with open(out_dir / f"{safe}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(out_dir / f"{safe}_notation_humaine.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "langue", "question", "reponse", "pertinence_1_5", "naturel_langue_1_5", "commentaire"])
        for r in rows:
            w.writerow([r["id"], r["language"], r["question"], r["reply"], "", "", ""])

    def acc(key, lang=None):
        sel = [r for r in rows if lang is None or r["language"] == lang]
        return round(100 * sum(r[key] for r in sel) / len(sel), 1) if sel else 0.0

    latencies = sorted(r["latency_s"] for r in rows)
    fee_items = [r for r in rows if r["intent"] == "frais"]
    return {
        "model": model,
        "intent_acc": acc("intent_ok"),
        **{f"intent_{l}": acc("intent_ok", l) for l in LANGS},
        "langid_acc": acc("langid_ok"),
        "lang_consistency": acc("lang_consistent"),
        "lang_exact": acc("lang_exact"),
        "errors": sum(bool(r["error"]) for r in rows),
        "fee_hallucination": round(100 * sum(r["fee_hallucination"] for r in fee_items) / max(len(fee_items), 1), 1),
        "latency_mean_s": round(statistics.mean(latencies), 2),
        "latency_p95_s": latencies[max(0, int(0.95 * len(latencies)) - 1)],
    }


def score(s: dict) -> float:
    """Score global /100 — pondération à justifier dans le rapport."""
    speed = max(0.0, 100 - 10 * s["latency_mean_s"])  # 0 s → 100, 10 s → 0
    return round(0.35 * s["intent_acc"] + 0.15 * s["langid_acc"] + 0.25 * s["lang_consistency"]
                 + 0.15 * (100 - s["fee_hallucination"]) + 0.10 * speed, 1)


def safe_name(model: str) -> str:
    return re.sub(r"[^\w.-]", "_", model)


def write_report(out_dir: Path) -> str:
    """summary.md : tous les modèles évalués dans ce dossier, triés par score."""
    summaries = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out_dir.glob("*_summary.json"))]
    summaries.sort(key=lambda s: s["score"], reverse=True)
    cols = ["model", "score", "intent_acc", "intent_fr", "intent_tn", "intent_arabizi", "langid_acc",
            "lang_consistency", "lang_exact", "fee_hallucination", "latency_mean_s", "latency_p95_s", "errors",
            "machine"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(s.get(c, "")) for c in cols) + " |" for s in summaries]
    report = "# Résultats de l'évaluation LLM\n\n" + "\n".join(lines) + (
        "\n\nMétriques en %, sauf latences (secondes). `fee_hallucination` : part des questions sur les frais où le "
        "modèle a inventé un montant (plus bas = mieux). `lang_consistency` : réponse en français pour une question "
        "en français, en dialecte/arabe sinon ; `lang_exact` : même variété exacte (tn ≠ arabizi). "
        "`errors` : appels échoués.\nCompléter avec la notation humaine (fichiers *_notation_humaine.csv).\n"
    )
    (out_dir / "summary.md").write_text(report, encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=[])
    parser.add_argument("--dataset", default=str(ROOT / "dataset.jsonl"))
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"))
    parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", "ollama"))
    parser.add_argument("--out-dir", default=str(ROOT / "results"))
    parser.add_argument("--machine", default="", help="machine utilisée (les latences en dépendent)")
    parser.add_argument("--skip-done", action="store_true", help="ne réévalue pas un modèle déjà présent")
    parser.add_argument("--summary-only", action="store_true", help="reconstruit summary.md sans appeler de modèle")
    args = parser.parse_args()
    if not args.models and not args.summary_only:
        parser.error("--models est obligatoire (sauf avec --summary-only)")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    items = [json.loads(line) for line in open(args.dataset, encoding="utf-8") if line.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for model in [] if args.summary_only else args.models:
        summary_path = out_dir / f"{safe_name(model)}_summary.json"
        if args.skip_done and summary_path.exists():
            print(f"\n=== {model} : déjà évalué, ignoré (--skip-done) ===")
            continue
        print(f"\n=== {model} ({len(items)} questions) ===")
        s = evaluate(model, items, args.base_url, args.api_key, out_dir)
        s["score"] = score(s)
        s["machine"] = args.machine
        s["questions"] = len(items)
        summary_path.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n" + write_report(out_dir))


if __name__ == "__main__":
    main()
