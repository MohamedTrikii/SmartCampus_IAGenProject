# Sprint 1 « Socle Technique » — revue de sprint

**Période** : 9 → 22 novembre 2026 · **Équipe** : Team 03 · **Dépôt** : https://github.com/MohamedTrikii/SmartCampus_IAGenProject

**Objectif du sprint** : poser les fondations techniques de SmartCampus AI (architecture, base relationnelle,
environnements backend et frontend, API, gestion des utilisateurs) ; sélectionner et intégrer un LLM pour les
premières fonctionnalités conversationnelles.

**Qualité mesurée (21/11/2026)** : 112 tests `pytest` verts ; migrations upgrade → downgrade → upgrade et
`alembic check` OK sur PostgreSQL 16 + pgvector ; `npm run build` OK ; synchronisation réelle de 5 sites :
24 formations créées, 2ᵉ passage sans changement.

## 1. État des 25 tâches et preuves

État au 21/11/2026 : **22 tâches faites** (à passer en *In review*), **2 en cours** (SA-33, SA-34), **1 faite avec réserve**
(SA-21 : données ISB absentes). Rien n'est encore *Done* : il faut le push, la CI verte et une relecture (Definition of Done).

| Story | Tâche | État | Preuve (fichier, test ou écran) |
|---|---|---|---|
| SA-2 Architecture et APIs | SA-3 Acteurs et processus métier | ✅ | `docs/acteurs-processus.md`, `docs/diagrammes/use-case-*.puml` |
| | SA-4 Architecture technique | ✅ | `docs/architecture.md` (composants, choix, 7 règles, séquence, environnements) |
| | SA-5 API et règles d'accès | ✅ | `docs/api.md`, `app/api/deps.py` (`require_roles`), `tests/test_auth.py` |
| SA-6 Init backend / frontend | SA-7 Initialiser le backend | ✅ | `backend/app/main.py`, `/health`, Swagger `/docs`, `tests/test_health.py` |
| | SA-8 Initialiser le frontend | ✅ | `frontend/` (chat, connexion, inscription, mon espace), `npm run build` |
| | SA-9 Environnement de développement local | ✅ | `docker-compose.yml` (+ GPU), `demarrer.bat`, `.env.example`, CI `.github/workflows/ci.yml` |
| SA-11 Modèle relationnel | SA-12 Tables du catalogue académique | ✅ | `institutions`, `programs`, `admission_requirements`, `program_fees` — `docs/modele-donnees.md` |
| | SA-13 Tables utilisateurs et candidatures | ✅ | `users`, `visitor_sessions`, `applications`, `recommendations`, `quizzes`, `appointments`… + `tests/test_workflow.py` |
| | SA-14 Tables documents et synchronisation | ✅ | `official_documents`, `catalog_sync_runs`, `attachments` |
| SA-15 PostgreSQL et migrations | SA-16 Installer et configurer PostgreSQL | ✅ | PostgreSQL 16 + pgvector (Docker, port 5433) |
| | SA-17 Tables et relations | ✅ | 3 migrations Alembic, upgrade/downgrade/upgrade + `alembic check` |
| | SA-18 Données de démonstration | ✅ | `scripts/seed.py` (admin) + 24 formations réelles synchronisées depuis les sites |
| SA-19 Catalogue et tarifs | SA-20 API des formations et programmes | ✅ | `GET/POST/PUT /programs`, droits par établissement, `tests/test_catalog.py` |
| | SA-21 API des tarifs et conditions d'admission | ✅ ⚠️ | `GET /programs/{code}` (frais `is_official`, conditions) — **ISB : 0 formation** (site anti-robot) |
| | SA-22 Fonctionnement et fiabilité des API | ✅ | 47 tests (catalogue, import, synchronisation dont 4 sur pages réelles), `docs/synchro-catalogue.md` |
| SA-24 Conversation sans compte | SA-25 Sessions des visiteurs | ✅ | `POST /sessions`, `X-Session-Id`, expiration, isolation — `tests/test_chat.py` |
| | SA-26 Mémoire temporaire des conversations | ✅ | `CHAT_HISTORY_WINDOW`, `scripts/purge_sessions.py`, `tests/test_retention_chat_connecte.py` |
| SA-27 Auth et rôles | SA-28 Authentification et rôles | ✅ | JWT + bcrypt, 6 rôles, `PATCH /users/{id}/role` (admin), `tests/test_auth.py` |
| | SA-29 Associer une conversation invitée à un compte | ✅ | rattachement à l'inscription / connexion, historique multi-appareils, écran *Mon espace* |
| SA-31 Évaluer et choisir le LLM | SA-32 Préparer les questions d'évaluation | ✅ | `llm-eval/dataset.jsonl` : 66 questions (22 FR, 22 TN, 22 Arabizi, 9 intentions) |
| | SA-33 Comparer les performances des modèles | 🟡 | banc `evaluate.py` + notebook Kaggle (15 modèles) prêts ; **exécution Kaggle à faire** |
| | SA-34 Évaluer tunisien et Arabizi | 🟡 | métriques par langue prêtes ; **résultats + notation humaine à faire** |
| SA-35 LLM et dialogue multi-tours | SA-36 Connecter le LLM au backend | ✅ | `app/llm/client.py`, `qwen2.5:3b` via Ollama (~7 s/réponse sur CPU) |
| | SA-37 Mémoire conversationnelle du LLM | ✅ | historique envoyé à chaque tour — `test_two_turn_conversation_keeps_history` |
| | SA-38 Tester le dialogue avec le LLM | ✅ | `tests/test_chat.py` + test réel (qualité Arabizi encore faible, cf. `docs/choix-llm.md`) |

## 2. Scénario de démo (5 minutes)

1. Double-clic sur `demarrer.bat` (LLM `qwen2.5:3b`) → http://localhost:3000 s'ouvre.
2. **Visiteur sans compte** : cliquer la suggestion *« chnowa el far9 bin prepa w licence ? »* → réponse en
   Arabizi, « langue détectée : Arabizi » sous la bulle.
3. Poser une 2ᵉ question qui renvoie à la 1ʳᵉ (« w el frais ? ») → mémoire multi-tours ; l'assistant précise
   que les frais du site sont indicatifs.
4. **Créer un compte** → « Mon espace » liste la conversation anonyme, désormais rattachée au compte.
5. **Déconnexion** puis **connexion** → l'historique revient ; sans connexion, la session rattachée renvoie 401.
6. **Swagger** (http://localhost:8000/docs, *Authorize* en admin) : `GET /programs?institution=IIT` (formations
   synchronisées depuis iit.tn, `source_url`), `GET /admin/catalog/sync-runs` (journal), puis un responsable IIT
   qui tente de modifier une formation ISB → 403 `OUT_OF_SCOPE`.
7. **Règles métier** : diagramme d'états de `docs/acteurs-processus.md` + `pytest tests/test_workflow.py -k ai`
   (l'IA ne peut ni accepter ni refuser).
8. **LLM** : `llm-eval/results/summary.md` et le modèle retenu.

## 3. Revue du projet : problèmes par gravité

Corrigés pendant la revue (faible risque) : mots de passe > 72 octets refusés (bcrypt les tronquait),
alerte au démarrage si `JWT_SECRET` est faible, `npm ci` dans le Dockerfile frontend, Next.js 14.2.18 → 14.2.35
(failles de sécurité publiées), mot de passe admin configurable (`ADMIN_PASSWORD`).

| # | Gravité | Problème | Proposition | À valider |
|---|---|---|---|---|
| 1 | Élevée | Catalogue **ISB vide** : isb.tn bloque les robots (« Security check ») alors que le sujet cible IIT + ISB | demander un export / l'autorisation du robot ; sinon saisie dans `data/catalogue.json` avec `source_url` | ☐ |
| 2 | Moyenne | Pas de limitation de débit sur `/auth/login` (force brute) ni `/chat/messages` (coût LLM) | limiter par IP et par session (ex. 10 messages/min) | ☐ |
| 3 | Moyenne | JWT stocké dans `localStorage` : volable en cas de faille XSS | cookie `HttpOnly` + `SameSite` au sprint 2 | ☐ |
| 4 | Moyenne | `JWT_SECRET` / `ADMIN_PASSWORD` par défaut utilisables hors dev (seulement une alerte) | refuser le démarrage si `APP_ENV=demo` avec des valeurs par défaut | ☐ |
| 5 | Moyenne | Synchro déclenchable plusieurs fois en parallèle via l'API | verrou (une seule synchro `running`) → 409 | ☐ |
| 6 | Faible | `409 EMAIL_ALREADY_USED` permet de tester si un email est inscrit | message neutre ou délai ; à arbitrer (UX) | ☐ |
| 7 | Faible | Conteneurs backend/scheduler lancés en root | utilisateur non root dans le Dockerfile | ☐ |
| 8 | Faible | Le user-agent est conservé pour les sessions anonymes | le supprimer ou le tronquer (minimisation RGPD / INPDP) | ☐ |
| 9 | Faible | `official_documents` contient les pages de contact (emails du personnel, publics) | exclure ces pages du corpus RAG | ☐ |
| 10 | Faible | Détection de langue heuristique : 60/66 (91 %) sur le jeu d'évaluation | la remplacer par le LLM retenu ou un classifieur | ☐ |
| 11 | Faible | Pas de tests automatisés du frontend ; parcours navigateur vérifié au niveau HTTP | 1 test Playwright du parcours de démo | ☐ |
| 12 | Info | Prompt injection possible (« ignore tes règles ») : sans impact tant que l'IA n'a pas d'outils | garde-fous avant les agents LangGraph (sprint 2) | ☐ |

Respect des règles du projet (`CONTRIBUTING.md`) : frontend → backend uniquement ✅ ; schéma via Alembic ✅ ; aucune décision officielle
ouverte à l'IA (testé) ✅ ; aucune donnée officielle inventée (TODO / null sinon) ✅ ; catalogue automatique ✅ ;
commits `SA-xx:` et branches `feature/SA-xx-…` ✅ (identifiants de **story** : les numéros des 25 tâches Visiora
n'étaient pas disponibles).

## 4. Ce qui reste à faire

| # | Tâche | Ticket | Qui |
|---|---|---|---|
| 1 | Pousser `main` et `develop` sur GitHub, protéger `main`, vérifier la CI | SA-9 | Mohamed TRIKI |
| 2 | Évaluation des 15 modèles sur Kaggle, rapport `docs/choix-llm.md` | SA-33, SA-34 | Skandar Soussi |
| 2 bis | Configurer le modèle retenu (`.env.example`) et vérifier le chat de bout en bout | SA-36 | Mohamed TRIKI |
| 3 | Notation humaine des réponses (2 notateurs par réponse) | SA-34 | les 4, coordonné par Skandar Soussi |
| 4 | Ajouter les vraies questions de lycéens recueillies au jeu d'évaluation | SA-32 | Skandar Soussi |
| 5 | Données ISB (site anti-robot) : demande officielle | SA-21 | Yassine Koubaa |
| 6 | Frontend : parcours de démo dans le navigateur + captures du rapport | SA-25, SA-26 | Yassine Koubaa |
| 7 | Validation de la conception, PNG des cas d'utilisation, du diagramme d'états et de l'architecture | SA-3, SA-4, SA-5, SA-12–14 | Ibrahim Ben Abdallah |
| 7 bis | Vérification des migrations sur PostgreSQL (aller-retour + `alembic check`) | SA-16, SA-17 | Mohamed TRIKI |
| 8 | Arbitrer les points 2 à 12 de la revue de sécurité | SA-5, SA-28 | Mohamed TRIKI |

## 5. Rétrospective

| Ce qui a bien marché | Ce qui a posé problème | Ce qu'on change au Sprint 2 |
|---|---|---|
| | | |
| | | |
| | | |

## 6. Préparation du Sprint 2 (RAG)

- **Corpus** : `official_documents` contient déjà les pages des 5 sites (texte, empreinte, date de changement),
  rafraîchies chaque jour par le scheduler. À ajouter : PDF officiels (brochures, règlements), validation par un
  responsable (`is_validated`).
- **Indexation** : découpage en passages, embeddings multilingues (FR/AR) dans pgvector (extension déjà activée),
  réindexation seulement des documents dont `content_hash` a changé.
- **Recherche** : remplacer `official_context()` de `routes_chat.py` par les k meilleurs passages, **avec citation
  de la source** dans la réponse ; même contrat API pour le frontend.
- **Évaluation** : relancer `llm-eval` avec le contexte RAG (`fee_hallucination` doit baisser) et ajouter des
  questions dont la réponse est dans le corpus.
- **Agents** : premier graphe LangGraph (orientation) appelant des outils du backend ; aucune décision officielle.
