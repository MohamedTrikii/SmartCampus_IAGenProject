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

Contraintes matérielles de l'équipe : [GPU disponible ? RAM des machines ? Colab ?]

## 2. Modèles évalués

| Modèle | Taille | Licence | Accès (Ollama / API) | Pourquoi |
|---|---|---|---|---|
| [ ] | [ ] | [ ] | [ ] | [ ] |
| [ ] | | | | |
| [ ] | | | | |

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

Coller ici `llm-eval/results/summary.md` :

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
