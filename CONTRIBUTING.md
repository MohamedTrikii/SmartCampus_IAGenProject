# SmartCampus AI — contexte projet

Projet N°3 IA générative, IIT Sfax 2026-2027, Team 03 (4 membres). Chatbot agentique d'orientation
universitaire (IIT : Licence, Prépa, Ingénierie ; ISB) en français, dialecte tunisien et Arabizi,
texte ou audio, jusqu'à la préinscription, au QCM, au rendez-vous et au suivi.
Suivi des tâches sur Project Supervision (Visiora), tickets SA-xx.
Dépôt : https://github.com/MohamedTrikii/SmartCampus_IAGenProject

## Stack
- backend/ : FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 + pgvector, Python 3.11
- frontend/ : Next.js 14 (App Router), TypeScript
- llm-eval/ : banc d'évaluation des LLM (FR / tunisien / Arabizi)
- LLM via API compatible OpenAI (Ollama en local), configuré dans .env
- IA à venir : LangGraph (agents), RAG pgvector, Whisper

## Documents de référence (à lire avant de modifier le domaine)
- docs/architecture.md : règles de communication entre composants
- docs/api.md : contrat API v1 (ne pas casser les routes existantes)
- docs/acteurs-processus.md : 6 processus métier et cycle de vie du dossier
- docs/modele-donnees.md : diagramme de classes
- backend/app/domain/workflow.py : SEULE façon de changer un statut (change_status)

## Règles
- Le frontend n'appelle que le backend (/api/v1). Jamais le LLM ni la base directement.
- Toute modification du schéma passe par une migration Alembic.
- L'IA ne prend jamais de décision officielle (acceptée / refusée / inscrit) : humain uniquement.
- Ne jamais inventer de données officielles (frais, moyennes, dates). Données à vérifier = TODO explicite.
- Le catalogue des formations vient AUTOMATIQUEMENT des sites officiels (backend/app/scraping, docs/synchro-catalogue.md) :
  on améliore l'extracteur (avec un test sur une page HTML réelle), on ne saisit pas les formations à la main.
- Chaque fonctionnalité a des tests pytest. Lancer `cd backend && pytest` avant de dire « terminé ».
- Messages de commit : `SA-xx: description`. Une branche par ticket : `feature/SA-xx-nom`, PR vers develop.
- Répondre en français. Rester cohérent avec le style du code existant.

## Commandes
- DB + LLM : `docker compose up -d db ollama`
- Backend : `cd backend && alembic upgrade head && python -m scripts.seed && uvicorn app.main:app --reload`
- Tests : `cd backend && pytest`
- Synchro du catalogue : `cd backend && python -m scripts.sync_sites --dry-run` (puis sans --dry-run)
- Frontend : `cd frontend && npm install && npm run dev`
