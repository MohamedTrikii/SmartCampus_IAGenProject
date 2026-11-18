# Modèle de données — diagramme de classes (SA-11, SA-15)

21 tables PostgreSQL 16 (+ extension `pgvector` activée pour le RAG du sprint 2).
Code : `backend/app/db/models.py` (socle) et `backend/app/db/models_workflow.py` (workflows métier).

Migrations Alembic (`backend/alembic/versions/`) :

| Révision | Contenu |
|---|---|
| `0001` | socle : utilisateurs, sessions visiteurs, établissements, formations, conditions, frais, conversations, messages, documents officiels ; active `vector` si disponible |
| `0002` | workflows métier : profils, préinscriptions, recommandations, équivalences, pièces, QCM, créneaux, RDV, entretiens, notifications, historique des statuts |
| `0003` | synchronisation automatique : `catalog_sync_runs`, empreintes et dates des pages, `data_source`, durée nullable |

Conventions : clés UUID pour les entités exposées à l'API (utilisateurs, sessions, conversations, messages,
dossiers), entiers pour les référentiels ; dates `timestamp with time zone` (UTC) ; **toutes les contraintes
uniques sont nommées** (`uq_<table>_<colonne>`) pour que les downgrades puissent les supprimer ; les
downgrades suppriment aussi les types enum PostgreSQL.

## 1. Socle (Sprint 1)

```mermaid
classDiagram
    direction LR

    class User {
      UUID id
      email (unique)
      password_hash
      full_name
      role : UserRole
      is_active
      created_at
    }
    class UserRole {
      <<enumeration>>
      candidate
      academic_iit
      academic_isb
      interviewer
      direction
      admin
    }
    class VisitorSession {
      UUID id
      user_id (nullable)
      preferred_language
      user_agent
      created_at
      last_seen_at
      expires_at
    }
    class Institution {
      code : IIT|ISB|ISA|2I2S|NAU
      name
      city
      website
    }
    class Program {
      code (unique)
      level : ProgramLevel
      name
      specialization
      duration_years (nullable)
      language
      career_outcomes : JSON
      bridges : JSON
      is_active
      source_url
      data_source : manual|scraped
      page_hash
      last_synced_at
    }
    class ProgramLevel {
      <<enumeration>>
      licence
      prepa
      ingenieur
      master
      autre
    }
    class AdmissionRequirement {
      bac_sections : JSON
      min_average
      required_diploma
      notes
    }
    class ProgramFee {
      academic_year
      fee_type
      amount
      currency
      is_official
    }
    class Conversation {
      UUID id
      title
      detected_language
      memory : JSON
    }
    class Message {
      UUID id
      role : user|assistant|system
      content
      language
      input_mode : text|audio
      latency_ms
      model
    }
    class OfficialDocument {
      title
      doc_type
      source_url (unique)
      content_text
      content_hash
      http_status
      is_validated
      last_fetched_at
      last_changed_at
    }
    class CatalogSyncRun {
      trigger : cli|schedule|api
      dry_run
      status : running|success|partial|failed
      started_at
      finished_at
      stats : JSON
      changes : JSON
      errors : JSON
    }

    User .. UserRole
    Program .. ProgramLevel
    User "0..1" -- "*" VisitorSession : rattachée après inscription
    VisitorSession "1" *-- "*" Conversation
    Conversation "1" *-- "*" Message
    Institution "1" -- "*" Program
    Institution "0..1" -- "*" OfficialDocument
    Program "1" *-- "*" AdmissionRequirement
    Program "1" *-- "*" ProgramFee : unique (programme, année, type)
```

## 2. Workflows métier (cf. `docs/acteurs-processus.md`)

```mermaid
classDiagram
    direction LR

    class User
    class Program
    class Conversation
    class CandidateProfile {
      bac_section
      bac_average
      favorite_subjects : JSON
      interests : JSON
      career_goal
      constraints
    }
    class Application {
      UUID id
      reference : PRE-AAAA-xxxxxx
      status : ApplicationStatus
      consent_given_at
      submitted_at
      last_candidate_activity_at
      reminder_count
      assigned_advisor_id
    }
    class Recommendation {
      rank
      compatibility_score
      justification
      sources : JSON
      status : proposee|validee|ajustee
      reviewed_by_id
    }
    class EquivalenceRequest {
      reference : EQV-AAAA-xxxxxx
      previous_institution
      previous_diploma
      status : EquivalenceStatus
      decided_at
    }
    class Attachment {
      doc_type
      storage_path
      is_verified
    }
    class Quiz {
      questions : JSON
      answers : JSON
      score
      summary_for_interviewer
      status
      deadline_at
    }
    class AvailabilitySlot {
      starts_at
      ends_at
      is_booked
    }
    class Appointment {
      starts_at
      status : AppointmentStatus
      reschedule_count (max 2)
    }
    class Interview {
      knowledge_score
      motivation_score
      observations
      result : InterviewResult
    }
    class Notification {
      type
      channel
      subject
      generated_by_ai
      status
    }
    class StatusHistory {
      entity_type
      entity_id
      old_status
      new_status
      actor_label
      comment
    }

    User "1" -- "0..1" CandidateProfile
    User "1" -- "*" Application : candidat
    Application "*" -- "0..1" Program : formation choisie
    Application "*" -- "0..1" Conversation : origine
    Application "1" *-- "*" Recommendation
    Recommendation "*" -- "1" Program
    User "1" -- "*" EquivalenceRequest
    Application "1" *-- "*" Attachment
    EquivalenceRequest "1" *-- "*" Attachment
    Application "1" *-- "*" Quiz
    User "1" -- "*" AvailabilitySlot : resp. entretien
    Application "1" -- "*" Appointment
    Appointment "*" -- "0..1" AvailabilitySlot
    Appointment "1" -- "0..1" Interview
    User "1" -- "*" Notification
    Application "1" -- "*" StatusHistory : historique
```

Règles d'intégrité notables :

- une pièce jointe appartient **soit** à une préinscription **soit** à une équivalence (`ck_attachment_single_owner`) ;
- un seul tarif par (formation, année universitaire, type de frais) (`uq_program_fees_program_year_type`) ;
- `programs.duration_years` est **nullable** : une durée non écrite sur le site officiel n'est jamais inventée ;
- les statuts ne changent que via `app/domain/workflow.py::change_status()`, qui écrit dans `status_history`.
