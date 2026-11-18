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

## Modèles candidats (open-source, gratuits, via Ollama)

Liste complète et à jour dans `kaggle_colab_eval.ipynb` (cellule 4). Un tag absent de la bibliothèque Ollama est
signalé puis sauté.

| Taille | Modèles (tags Ollama) | Pourquoi |
|---|---|---|
| ≤ 4B | `qwen2.5:3b`, `llama3.2:3b`, `gemma2:2b`, `phi3.5:3.8b`, `qwen3:4b`, `gemma3:4b` | tournent sur un PC sans gros GPU (`qwen2.5:3b` : ~7 s/réponse sur CPU i7) |
| 7–9B | `qwen2.5:7b-instruct`, `qwen3:8b`, `llama3.1:8b`, `mistral:7b`, `aya-expanse:8b`, `command-r7b-arabic:7b`, `gemma2:9b` | candidats principaux ; Aya et Command R7B Arabic sont conçus pour l'arabe ; tous adaptables en LoRA |
| 12B | `mistral-nemo:12b`, `gemma3:12b` | limite haute d'un GPU T4 16 Go |

Exclus volontairement : **GPT-2** (pas conversationnel, ne suit pas d'instructions, presque uniquement anglais,
contexte de 1 024 tokens : notre prompt n'y tient pas), les modèles *base* non instruits, et les modèles de
raisonnement (`deepseek-r1`) dont les balises `<think>` cassent la sortie JSON.

Le sujet demande d'**adapter au moins un modèle** (LoRA/QLoRA) au tunisien et à l'Arabizi : ce banc sert de baseline,
on relancera le même script sur le modèle adapté pour mesurer le gain.

## Où lancer l'évaluation : PC local ou Kaggle / Colab ?

| Option | Matériel | Modèles réalistes | Quand l'utiliser |
|---|---|---|---|
| PC local (ex. RTX 3050 4 Go, 16 Go RAM) | GPU 4 Go via `docker-compose.gpu.yml` | 2–3B entièrement sur GPU (`qwen2.5:3b`, `llama3.2:3b`, `gemma2:2b`) ; 7B possible mais en partie sur CPU, donc lent | développement, démo, petit banc |
| **Kaggle** (recommandé pour SA-31) | GPU T4 16 Go, ~30 h/semaine gratuites | 7–9B (`qwen2.5:7b-instruct`, `llama3.1:8b`, `gemma2:9b`, `aya-expanse:8b`) | comparaison sérieuse des modèles, plus tard fine-tuning LoRA |
| Colab gratuit | GPU T4, sessions plus courtes et interruptibles | idem Kaggle | dépannage |

Notebook prêt à l'emploi : `llm-eval/kaggle_colab_eval.ipynb`. Il installe Ollama sur le GPU du notebook puis, pour chaque
modèle : téléchargement → **même** `evaluate.py` sur le **même** `dataset.jsonl` → suppression du modèle (le disque ne se
remplit pas). Reprise automatique si la session coupe (`--skip-done`), tableau final avec `--summary-only`. Les latences dépendent de la machine : toujours préciser le GPU dans
`docs/choix-llm.md`, et ne comparer entre eux que des modèles évalués sur la même machine.

L'application (chat) reste sur Ollama local, ou sur une API compatible OpenAI en changeant seulement
`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` dans `.env`.

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
