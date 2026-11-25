# Évaluation et choix du modèle de langage (SA-31)

> **À compléter par l'équipe** après avoir lancé `llm-eval/evaluate.py` (voir `llm-eval/README.md`).
> Les parties entre `[ ]` sont à remplir avec VOS résultats. Ne jamais recopier de chiffres non mesurés.
> Ce document sert directement pour la partie « Résultats & validation » de la présentation.

## 1. Besoin

SmartCampus AI doit comprendre et répondre à des futurs étudiants tunisiens :
- en **français**, en **dialecte tunisien** (lettres arabes) et en **Arabizi** (lettres latines + chiffres 3, 7, 9, 5), souvent mélangés (code-switching) ;
- sans **inventer** d'informations officielles (frais, conditions, dates) ;
- avec une latence acceptable pour un chat (objectif : moins de [ ] secondes en moyenne) ;
- avec un modèle **open-source** adaptable par LoRA/QLoRA (exigence du sujet).

Contraintes matérielles de l'équipe : PC portable i7, 16 Go RAM, RTX 3050 4 Go ; dans Docker, Ollama tourne
sur le CPU seul (GPU non utilisé). Kaggle / Colab (GPU T4 16 Go) pour les modèles 7–12B.

## 2. Modèles évalués

| Modèle | Taille | Licence | Accès (Ollama / API) | Pourquoi | État |
|---|---|---|---|---|---|
| `qwen2.5:3b` | 3,1 B (Q4_K_M) | Qwen Research License | Ollama local | modèle par défaut du chat, multilingue dont l'arabe | ✅ évalué (poste local) |
| `gemma2:2b` | 2,6 B (Q4_0) | Gemma Terms of Use | Ollama local | plus petit candidat, le plus léger sur CPU | ⏳ à évaluer (poste local) |
| `llama3.2:3b` | 3,2 B | Llama 3.2 Community License | Ollama local | référence Meta de même taille | ⏳ à évaluer (poste local) |
| modèles 7–12B | | | Kaggle T4 (`llm-eval/kaggle_colab_eval.ipynb`) | candidats principaux | ⏳ à évaluer |

## 3. Protocole

- **Jeu de test** : [N] questions (`llm-eval/dataset.jsonl`), réparties à parts égales entre FR, tunisien et Arabizi,
  couvrant 9 intentions (infos formation, conditions, frais, comparaison, orientation, préinscription, rendez-vous,
  salutation, hors-sujet). [N] questions écrites par l'équipe, [N] recueillies auprès de lycéens.
- **Mêmes conditions pour tous les modèles** : même prompt système, même contexte, température 0 pour la
  classification et 0,3 pour la génération, même machine.
- **Métriques automatiques** : `intent_acc` (compréhension), `langid_acc` (identification de la langue),
  `lang_consistency` (répond dans la langue du candidat), `fee_hallucination` (invente un montant),
  latence moyenne et p95.
- **Évaluation humaine** : [N] évaluateurs notent de 1 à 5 la pertinence et le naturel de la langue
  (fichiers `results/*_notation_humaine.csv`), moyenne des notes.
- **Score global** : 35 % compréhension, 15 % identification de langue, 25 % cohérence de langue,
  15 % absence d'hallucination, 10 % rapidité. Pondération choisie parce que [justification].

## 4. Résultats

### 4.0 Mesure préliminaire sur poste local

Premiers essais à la main, avant le banc complet : ils servent à choisir la machine d'évaluation.

| Machine | Modèle | Exécution | Question | Latence | Langue de la réponse |
|---|---|---|---|---|---|
| PC portable, RTX 3050 4 Go, 16 Go RAM (7,6 Go alloués à Docker) | `gemma2:2b` (Ollama 0.40, Docker) | CPU (GPU non initialisé dans le conteneur) | « chnowa el far9 bin prepa w licence ? » + contexte officiel (24 formations) | 264 s (1er chargement du modèle compris) | français (question en Arabizi) |
| même poste, CPU (`ollama ps` : 100 % CPU) | `qwen2.5:3b` | backend complet (prompt système + contexte officiel) | « Quelle est la différence entre la Prépa et la Licence ? » | 7 s | français ✓ — contenu imprécis : présente la Prépa comme une préparation à la Licence |
| même poste, CPU | `qwen2.5:3b` | idem, 2ᵉ tour | « chnowa el far9 bin prepa w licence ? » | 8 s | mélange Arabizi / français (« El far9 bin prépa est un cycle… ») |

Conclusion : un modèle 3B répond en quelques secondes sur ce poste (utilisable pour le développement et la démo),
mais la qualité en Arabizi et l'exactitude sont insuffisantes sur ces deux exemples. Les modèles 7–9B sont évalués
sur un GPU T4 Kaggle avec `llm-eval/kaggle_colab_eval.ipynb`.

### 4.1 Banc complet sur poste local (modèles ≤ 3B)

Machine : PC portable i7, 16 Go RAM, CPU seul (Ollama dans Docker, 7,6 Go alloués, d'autres conteneurs actifs).
66 questions (22 FR, 22 tunisien, 22 Arabizi). Résultats bruts : `llm-eval/results/summary.md` et `*.jsonl`.

| model | score | intent_acc | intent_fr | intent_tn | intent_arabizi | langid_acc | lang_consistency | lang_exact | fee_hallucination | latency_mean_s | latency_p95_s | errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `qwen2.5:3b` | 59.3 | 66.7 | 81.8 | 68.2 | 50.0 | 21.2 | 71.2 | 42.4 | 0.0 | 20.56 | 180.0 | 5 |
| `gemma2:2b` | ⏳ | | | | | | | | | | | |
| `llama3.2:3b` | ⏳ | | | | | | | | | | | |

Métriques en %, latences en secondes. Lecture pour `qwen2.5:3b` :
- **5 appels échoués sur 66** (4 dépassements du délai de 180 s, 1 erreur 500 d'Ollama), comptés comme faux et à
  180 s : ils tirent la latence moyenne et le p95 vers le haut. Sur les 61 réponses obtenues : latence moyenne
  **7,5 s**, médiane **4,5 s**. Cause probable : machine chargée (CPU seul, autres conteneurs actifs).
- **Arabizi à 50 %** de compréhension : sous le seuil de 60 % fixé au §3 ; le modèle ne peut pas être retenu tel quel.
- **Identification de la langue faible (21,2 %)** : le modèle confond souvent tunisien, Arabizi et français.
- **Aucun montant de frais inventé** (0 %) avec le contexte fourni.

Les latences de ce tableau ne se comparent pas à celles de Kaggle (machine différente).

### 4.2 Banc Kaggle (modèles 7–12B, à remplir après l'exécution)

Machine : [GPU]. Coller ici `llm-eval/results/summary.md` :

| model | score | intent_acc | intent_fr | intent_tn | intent_arabizi | langid_acc | lang_consistency | lang_exact | fee_hallucination | latency_mean_s | latency_p95_s | errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [ ] | | | | | | | | | | | | |

Évaluation humaine (moyenne /5) :

| Modèle | Pertinence FR | Pertinence TN | Pertinence Arabizi | Naturel de la langue |
|---|---|---|---|---|
| [ ] | | | | |

## 5. Analyse

- **Écart entre langues** : [ex. tous les modèles perdent X points en Arabizi par rapport au français]
- **Erreurs fréquentes** : [ex. confusion entre « comparaison » et « orientation personnalisée » ; réponses en
  français à des questions en Arabizi ; ...] — donner 2 ou 3 exemples réels tirés de `results/*.jsonl`.
- **Hallucinations** : [ex. le modèle X a inventé des frais dans N cas sur M]
- **Latence** : [ ]

## 6. Décision

**Modèle retenu : [ ]**, parce que [2 à 3 raisons appuyées par les chiffres ci-dessus].

Configuration : `LLM_MODEL=[ ]` dans `.env`.

## 7. Limites et suite

- Limites du protocole : jeu de test encore petit ; détection automatique de langue heuristique (environ 86 %
  sur le jeu de test) ; [ ].
- **Adaptation prévue (Sprint 5)** : fine-tuning LoRA/QLoRA de [modèle] sur un corpus de questions-réponses
  tunisien/Arabizi sur les formations, puis **même banc de test** pour mesurer le gain (avant/après).
- Le RAG (Sprint 2) réduira les hallucinations sur les informations officielles : on mesurera à nouveau
  `fee_hallucination` avec le contexte RAG.

## 8. Plan d'adaptation LoRA (à détailler au Sprint 5)

| Étape | Contenu | Chiffres à renseigner |
|---|---|---|
| Données | questions-réponses FR / tunisien / Arabizi sur les formations, validées par l'équipe | [ ] paires, dont [ ] en Arabizi |
| Méthode | QLoRA 4 bits sur [modèle de base], rang [ ], [ ] époques | GPU utilisé : [ ] |
| Évaluation | **même** `evaluate.py` et même `dataset.jsonl`, avant / après | gain `intent_arabizi` : [ ] points |
| Critère | adopter le modèle adapté seulement s'il améliore le score sans augmenter `fee_hallucination` | [ ] |
