# Résultats de l'évaluation LLM

| model | score | intent_acc | intent_fr | intent_tn | intent_arabizi | langid_acc | lang_consistency | lang_exact | fee_hallucination | latency_mean_s | latency_p95_s | errors | machine |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5:3b | 59.3 | 66.7 | 81.8 | 68.2 | 50.0 | 21.2 | 71.2 | 42.4 | 0.0 | 20.56 | 180.0 | 5 | PC portable i7, 16 Go RAM, CPU seul (Ollama Docker) |

Métriques en %, sauf latences (secondes). `fee_hallucination` : part des questions sur les frais où le modèle a inventé un montant (plus bas = mieux). `lang_consistency` : réponse en français pour une question en français, en dialecte/arabe sinon ; `lang_exact` : même variété exacte (tn ≠ arabizi). `errors` : appels échoués.
Compléter avec la notation humaine (fichiers *_notation_humaine.csv).
