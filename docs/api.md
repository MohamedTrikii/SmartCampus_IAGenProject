# Contrat API v1 — SmartCampus AI (SA-2)

Base URL : `http://localhost:8000/api/v1` — documentation interactive : `http://localhost:8000/docs`
(bouton **Authorize** : email dans `username`, mot de passe dans `password`).

Conventions : JSON `snake_case`, UUID, dates ISO 8601 UTC (voir `docs/architecture.md` §3).

Légende des accès :

| Symbole | Signification |
|---|---|
| 🌐 | public, sans identification |
| 👤 | visiteur (`X-Session-Id`) **ou** utilisateur connecté (`Authorization: Bearer <jwt>`) |
| 🔒 | JWT obligatoire (+ rôles indiqués) |

## Rôles

| Rôle (`role`) | Acteur du sujet | Périmètre |
|---|---|---|
| `candidate` | Candidat identifié | ses conversations, (plus tard) son dossier |
| `academic_iit` | Responsable académique IIT | catalogue IIT, dossiers IIT |
| `academic_isb` | Responsable académique ISB | catalogue ISB, dossiers ISB |
| `interviewer` | Responsable entretien | créneaux, RDV, entretiens |
| `direction` | Direction | consultation, tableaux de bord |
| `admin` | Administrateur plateforme | tout, gestion des rôles, synchronisation |

Le **visiteur anonyme n'est pas un rôle** : c'est une `visitor_session` sans utilisateur. Tout compte créé
via `/auth/register` reçoit le rôle `candidate` ; seul un `admin` peut changer un rôle.

## Format d'erreur (toutes les routes)

```json
{ "detail": "Formation introuvable", "code": "PROGRAM_NOT_FOUND" }
```

Validation (422) : `{"detail": "Données invalides", "code": "VALIDATION_ERROR", "errors": [{"field": "body.email", "message": "..."}]}`

| HTTP | Codes possibles |
|---|---|
| 400 | `SESSION_ID_MISSING`, `SESSION_ID_INVALID`, `UNKNOWN_INSTITUTION`, `UNKNOWN_SITE`, `BAD_REQUEST` |
| 401 | `NOT_AUTHENTICATED`, `INVALID_TOKEN`, `INVALID_CREDENTIALS`, `SESSION_EXPIRED` |
| 403 | `FORBIDDEN`, `OUT_OF_SCOPE` |
| 404 | `NOT_FOUND`, `USER_NOT_FOUND`, `PROGRAM_NOT_FOUND`, `CONVERSATION_NOT_FOUND` |
| 409 | `EMAIL_ALREADY_USED`, `PROGRAM_CODE_ALREADY_USED` |
| 422 | `VALIDATION_ERROR` |
| 503 | `LLM_UNAVAILABLE` |

## Sprint 1 — endpoints implémentés

### Santé (SA-6)
| Méthode | Route | Accès | Réponse |
|---|---|---|---|
| GET | `/health` | 🌐 | `{"status":"ok"}` |

### Sessions visiteurs (SA-24)
| Méthode | Route | Accès | Corps / réponse |
|---|---|---|---|
| POST | `/sessions` | 🌐 | aucun corps, **aucune donnée personnelle** → `201 {"session_id","expires_at","user_id":null}` |
| GET | `/sessions/me` | `X-Session-Id` | → `{"session_id","expires_at","user_id"}` · 400 si absent/invalide · 401 si expirée |

### Authentification et rôles (SA-27)
| Méthode | Route | Accès | Corps / réponse |
|---|---|---|---|
| POST | `/auth/register` | 🌐 (+ `X-Session-Id` facultatif) | `{"email","password" (≥ 8),"full_name"}` → `201 UserOut` (rôle `candidate`). Si `X-Session-Id` est fourni, la session anonyme est **rattachée** au compte (historique conservé). 409 si email déjà utilisé. |
| POST | `/auth/login` | 🌐 | formulaire OAuth2 `username` (email), `password` → `{"access_token","token_type":"bearer"}` · 401 sinon |
| GET | `/auth/me` | 🔒 tous rôles | → `UserOut {"id","email","full_name","role","created_at"}` |
| PATCH | `/users/{id}/role` | 🔒 `admin` | `{"role"}` → `UserOut` · 403 pour les autres rôles · 404 si inconnu |

### Catalogue (SA-19)
| Méthode | Route | Accès | Description |
|---|---|---|---|
| GET | `/institutions` | 🌐 | IIT, ISB, ISA, 2I2S, NAU |
| GET | `/programs?institution=IIT&level=licence` | 🌐 | formations actives, filtres facultatifs (`level` : licence, prepa, ingenieur, master, autre) |
| GET | `/programs/{code}` | 🌐 | détail : conditions d'accès, frais (`is_official`), débouchés, `source_url`, `data_source`, `last_synced_at` · 404 |
| POST | `/programs` | 🔒 `admin`, `academic_iit`*, `academic_isb`* | création (saisie **manuelle**, verrouillée : `data_source=manual`) · 409 si code déjà utilisé |
| PUT | `/programs/{code}` | 🔒 idem* | mise à jour (les frais et conditions sont remplacés) · passe la formation en `manual` |

\* un responsable IIT ne gère que les formations IIT, un responsable ISB que l'ISB (403 `OUT_OF_SCOPE` sinon) ;
les formations ISA, 2I2S et NAU ne sont modifiables que par `admin`.

### Synchronisation automatique du catalogue (SA-19)
| Méthode | Route | Accès | Description |
|---|---|---|---|
| GET | `/admin/catalog/sources` | 🔒 `admin`, `academic_iit`, `academic_isb`, `direction` | sites synchronisés (code, nom, URL) |
| POST | `/admin/catalog/sync?site=IIT&dry_run=true` | 🔒 `admin` | lance une synchronisation en tâche de fond → `202` ; `site` répétable (tous par défaut) ; 400 `UNKNOWN_SITE` |
| GET | `/admin/catalog/sync-runs?limit=20` | 🔒 `admin`, `academic_iit`, `academic_isb`, `direction` | journal : statut, statistiques par site, changements (avant/après), erreurs |

Voir `docs/synchro-catalogue.md`.

### Conversation (SA-35, SA-24, SA-27)
| Méthode | Route | Accès | Corps / réponse |
|---|---|---|---|
| POST | `/chat/messages` | 👤 | `{"message" (1–4000), "conversation_id"?}` → `{"conversation_id","reply","language"}` (`fr`, `ar`, `tn`, `arabizi`) · 503 `LLM_UNAVAILABLE` |
| GET | `/chat/conversations` | 👤 | conversations visibles (voir règles ci-dessous), plus récentes d'abord |
| GET | `/chat/conversations/{id}/messages` | 👤 | historique ordonné · 404 si la conversation n'est pas visible |

Règles de visibilité :

- **Visiteur anonyme** (session non rattachée) : uniquement les conversations de **sa** session.
- **Session rattachée à un compte** ou **JWT** : toutes les conversations de toutes les sessions du compte
  (un candidat retrouve son historique sur un nouvel appareil).
- **JWT + `X-Session-Id` non rattaché** : la session est rattachée au compte à ce moment-là.
- Avec un JWT sans session, `POST /chat/messages` crée automatiquement une session rattachée au compte.
- Une session déjà rattachée à un **autre** compte est refusée (403).
- Rétention : les sessions anonymes expirées sont purgées chaque jour (voir `docs/architecture.md` §6).

## Sprints suivants — routes réservées (ne pas réutiliser ces chemins)

| Route | Epic prévue |
|---|---|
| `POST /chat/audio` | Voix (Whisper STT / TTS) |
| `GET/PUT /candidates/me/profile` | Profil candidat |
| `POST /orientation/recommendations`, `PATCH /recommendations/{id}` | Agent d'orientation + RAG, validation humaine |
| `POST /applications`, `GET /applications/{ref}`, `POST /applications/{ref}/status` | Préinscription + consentement (machine à états) |
| `POST /applications/{ref}/attachments` | Pièces justificatives |
| `POST /equivalences`, `POST /equivalences/{ref}/status` | Demandes d'équivalence |
| `POST /quizzes`, `POST /quizzes/{id}/answers` | QCM personnalisé |
| `GET/POST /availability-slots`, `POST /appointments`, `PATCH /appointments/{id}` | Rendez-vous |
| `POST /interviews/{id}/decision` | Entretien et décision |
| `GET /notifications` | Notifications et relances |
| `GET /dashboard/stats` | Dashboard direction |
| `POST /rag/documents`, `GET /rag/search` | Administration du corpus RAG |
