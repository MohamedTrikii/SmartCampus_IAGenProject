## Ticket
SA-<!-- numéro de la tâche Project Supervision (ex. SA-12) -->

## Description
<!-- Ce qui change et pourquoi (2 à 5 lignes) -->

## Comment tester
1. <!-- commandes ou parcours à suivre, ex. `cd backend && pytest tests/test_chat.py` -->
2.

## Captures / extraits (si interface ou rapport)

## Checklist
- [ ] Branche `feature/SA-xx-…` vers `develop`, commits `SA-xx: …`
- [ ] `cd backend && pytest` passe ; la CI est verte
- [ ] `cd frontend && npm run build` passe (si frontend modifié)
- [ ] Migration Alembic ajoutée, upgrade **et** downgrade testés (si schéma modifié)
- [ ] `docs/api.md` mis à jour (si API modifiée) ; routes existantes non cassées
- [ ] Aucune donnée officielle inventée (frais, dates, conditions) ; aucun secret ni `.env` commité
- [ ] L'IA ne prend aucune décision officielle (statuts via `change_status()` uniquement)
- [ ] Relu et approuvé par un autre membre
