# Évaluation et sélection du LLM (SA-31)

## Protocole

1. **Jeu de test** `dataset.jsonl` : 36 questions (12 FR, 12 tunisien en lettres arabes, 12 Arabizi), les mêmes
   intentions dans les 3 langues pour une comparaison équitable. Intentions : informations sur une formation,
   conditions d'accès, frais, comparaison, orientation personnalisée, préinscription, rendez-vous, salutation, hors-sujet.
   → **À enrichir par l'équipe** (objectif : 100+ questions, formulations réelles d'amis ou de cousins lycéens).
2. **Métriques automatiques** (`evaluate.py`) :

| Métrique | Ce qu'elle mesure | Poids dans le score |
|---|---|---|
| `intent_acc` (+ détail par langue) | compréhension de la demande | 35 % |
| `langid_acc` | reconnaissance FR / tunisien / Arabizi | 15 % |
| `lang_consistency` | répond dans la langue du candidat | 25 % |
| `fee_hallucination` | invente un montant non fourni (↓ = mieux) | 15 % |
| `latency_mean_s`, `p95` | temps de réponse | 10 % |
| `lang_exact` | même variété exacte (tunisien ≠ Arabizi) | information (hors score) |
| `errors` | appels échoués (timeout, erreur HTTP) : comptés comme faux | information (hors score) |

3. **Notation humaine** : chaque membre note 1–5 la *pertinence* et le *naturel de la langue* dans
   `results/<modele>_notation_humaine.csv` (au moins 2 notateurs par réponse, on fait la moyenne).
4. **Décision** : modèle retenu = meilleur score global, sans être sous 60 % d'`intent_acc` en Arabizi.
   Le résultat va dans le rapport et la présentation (partie « Résultats & validation »).

## Modèles candidats proposés (open-source, via Ollama)

| Modèle | Tag Ollama | Pourquoi le tester |
|---|---|---|
| Qwen2.5 7B Instruct | `qwen2.5:7b-instruct` | très bon multilingue / arabe à cette taille |
| Llama 3.1 8B Instruct | `llama3.1:8b` | référence open-source, base courante pour LoRA |
| Gemma 2 9B | `gemma2:9b` | bon en français |
| Aya Expanse 8B | `aya-expanse:8b` | modèle conçu pour le multilingue, dont l'arabe |
| Mistral NeMo 12B | `mistral-nemo` | bon en français, plus lourd |

Vérifiez la disponibilité des tags (`ollama pull <tag>`) et la RAM/VRAM de vos machines : un 7–9B en
quantification Q4 demande environ 6 à 8 Go. Sans GPU, une API compatible OpenAI (Groq, OpenRouter...) peut servir à
évaluer des modèles plus gros : il suffit de changer `LLM_BASE_URL`, `LLM_API_KEY` et le nom du modèle.

Le sujet demande aussi d'**adapter au moins un modèle** (LoRA/QLoRA) au tunisien et à l'Arabizi. Ce banc de test sert
de baseline : on relancera exactement le même script sur le modèle fine-tuné pour mesurer le gain.

## Lancer

```bash
pip install httpx
ollama pull qwen2.5:7b-instruct && ollama pull llama3.1:8b && ollama pull gemma2:9b
python evaluate.py --models qwen2.5:7b-instruct llama3.1:8b gemma2:9b
# → results/summary.md (tableau comparatif) + un .jsonl et un .csv par modèle
python evaluate.py --models fake   # vérifier le script sans LLM
```

> Limite connue : la détection de langue des réponses est une heuristique (31/36 = 86 % de bonnes détections sur les 36 questions initiales, mesuré le 18/11/2026).
> Vérifiez à la main les cas où `lang_consistent` est faux.
