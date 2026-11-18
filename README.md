# SmartCampus AI — Plateforme agentique d'orientation universitaire

Projet N°3 — IA générative — IIT Sfax 2026-2027 — Team 03
Dépôt : https://github.com/MohamedTrikii/SmartCampus_IAGenProject

Chatbot agentique qui oriente les futurs étudiants (Licence, Prépa, Ingénierie IIT, formations ISB, ISA,
2I2S, NAU) en français, dialecte tunisien et Arabizi, par texte ou audio, jusqu'à la préinscription,
le QCM, le rendez-vous d'entretien et le suivi. L'IA conseille ; **les décisions officielles restent humaines**.

Sprint 1 « Socle Technique » (9 → 22 nov. 2026) : architecture, base relationnelle, catalogue synchronisé
automatiquement depuis les sites officiels, sessions anonymes, authentification et rôles, intégration et
évaluation du LLM.

## Arborescence

```
smartcampus-ai/
├── demarrer.bat / .ps1    # lancement en un clic (Windows)
├── docker-compose.yml     # db (PostgreSQL 16 + pgvector), ollama, backend, scheduler, frontend
├── docker-compose.gpu.yml # option GPU NVIDIA pour Ollama
├── .env.example           # variables d'environnement commentées (copier en .env)
├── data/
│   └── catalogue.json     # corrections MANUELLES du catalogue (verrouillées), monté en lecture seule
├── docs/                  # architecture, contrat API, processus métier, modèle de données, synchro, choix LLM
│   └── diagrammes/        # cas d'utilisation (PlantUML), états et classes
├── backend/               # FastAPI + SQLAlchemy 2 + Alembic (Python 3.11)
│   ├── app/
│   │   ├── api/           # routes : sessions, auth, catalogue, chat, admin
│   │   ├── core/          # configuration, sécurité (JWT, bcrypt, rôles)
│   │   ├── db/            # modèles ORM (socle + workflows métier), session
│   │   ├── domain/        # machine à états des dossiers (change_status)
│   │   ├── llm/           # client LLM compatible OpenAI, détection de langue
│   │   └── scraping/      # synchronisation automatique depuis iit.tn, isb.tn, isa.tn, 2i2s.tn, nau.tn
│   ├── alembic/           # migrations
│   ├── scripts/           # seed, import_catalogue, sync_sites, scheduler, purge_sessions
│   └── tests/             # pytest (SQLite en mémoire, LLM simulé, sites simulés)
├── frontend/              # Next.js 14 (App Router, TypeScript) : chat, connexion, inscription, mon espace
├── llm-eval/              # banc d'évaluation des LLM FR / tunisien / Arabizi
└── .github/               # CI GitHub Actions, modèle de Pull Request
```

## Lancer le projet en un clic (Windows)

Double-cliquer sur **`demarrer.bat`** (ou `.\demarrer.ps1` dans PowerShell). Le script démarre Docker Desktop si
besoin, crée `.env`, construit et lance les 5 services, attend le backend, synchronise le catalogue s'il est vide,
puis ouvre http://localhost:3000.

| Commande | Effet |
|---|---|
| `demarrer.bat` | LLM réel si le modèle de `.env` est installé dans Ollama, sinon LLM simulé |
| `demarrer.bat -Fake` | LLM simulé : réponses instantanées, pour montrer l'interface |
| `demarrer.bat -Modele gemma2:2b` | LLM réel avec ce modèle (téléchargé si absent ; sans GPU : 1 à 5 min par réponse) |
| `demarrer.bat -Gpu` | GPU NVIDIA pour Ollama (`docker-compose.gpu.yml`) |
| `demarrer.bat -Synchro` | relance la synchronisation du catalogue depuis les sites officiels |
| `demarrer.bat -Arreter` | arrête les services (données conservées) |

Compte admin de démo pour Swagger (http://localhost:8000/docs) : `ADMIN_EMAIL` / `ADMIN_PASSWORD` de `.env`.

## Démarrage rapide (développement, sans le script)

Prérequis : Docker Desktop, Python 3.11+, Node 20+.

```bash
cp .env.example .env                       # puis changer JWT_SECRET
docker compose up -d db ollama              # PostgreSQL publié sur le port 5433 du poste
docker compose exec ollama ollama pull qwen2.5:3b

cd backend
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python -m scripts.seed
python -m scripts.sync_sites --dry-run     # rapport de synchro sans rien écrire (puis sans --dry-run)
uvicorn app.main:app --reload              # http://localhost:8000/docs

cd ../frontend
npm install && npm run dev                 # http://localhost:3000
```

Tout en Docker : `docker compose up -d --build` (frontend :3000, backend :8000).

Tests backend : `cd backend && pytest` (SQLite en mémoire, LLM et sites simulés : ni Docker ni internet).

## Conventions Git

- Branches : `main` (stable, protégée) ← `develop` (intégration) ← `feature/SA-xx-description`
- Une branche par ticket Project Supervision ; Pull Request vers `develop`, relue par au moins 1 membre
- Commits : `SA-xx: description` (relie le commit au ticket)
- `develop` → `main` en fin de sprint, après la revue

## Definition of Done

Un ticket est terminé quand :

1. le code est mergé dans `develop` via une PR relue ;
2. `cd backend && pytest` passe et la CI est verte (tests, migrations, build frontend) ;
3. toute modification du schéma a sa migration Alembic (upgrade **et** downgrade testés) ;
4. les nouveaux endpoints apparaissent dans Swagger (`/docs`) et dans `docs/api.md` ;
5. aucune donnée officielle inventée (frais, dates, conditions) ; aucun secret commité ;
6. le ticket est passé en *In review* sur Project Supervision.

> Le catalogue des formations est **synchronisé automatiquement** depuis les sites officiels
> (service `scheduler`, toutes les `SYNC_INTERVAL_HOURS`). Voir `docs/synchro-catalogue.md`.
