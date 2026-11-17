# Répartition du travail — Sprint 1 « Socle Technique »

Équipe : **Mohamed TRIKI**, **Skandar Soussi**, **Ibrahim Ben Abdallah**, **Yassine Koubaa**.

Le code des 25 tâches est écrit et testé (112 tests verts). Il reste à **valider, mesurer et présenter** : chaque
membre devient responsable d'un bloc de tâches sur Project Supervision, vérifie sur son PC que c'est bien fait,
complète ce qui manque et le présente à la revue.

## 1. Qui est responsable de quoi

| Membre | Tâches | Domaine |
|---|---|---|
| **Mohamed TRIKI** | SA-7, SA-8, SA-9, SA-16, SA-17, SA-28, SA-29, SA-36 | socle technique : backend, initialisation du frontend, environnement et CI, base PostgreSQL et migrations, authentification et rôles, intégration du LLM ; coordination |
| **Ibrahim Ben Abdallah** | SA-3, SA-4, SA-5, SA-12, SA-13, SA-14 | **conception** : acteurs et processus, architecture technique, contrat API et règles d'accès, conception des tables |
| **Skandar Soussi** | SA-32, SA-33, SA-34, SA-37, SA-38 | suite de l'intégration du LLM : jeu de questions, comparaison des modèles, tunisien / Arabizi, mémoire et tests du dialogue |
| **Yassine Koubaa** | SA-18, SA-20, SA-21, SA-22, SA-25, SA-26 | frontend (parcours, pages, ergonomie), données de démonstration, API catalogue et tarifs, sessions visiteurs |

Relectures croisées : Mohamed ↔ Ibrahim, Skandar ↔ Yassine (chaque PR est relue par un autre membre).

## 2. À faire d'ici la revue du 22 novembre

Tout le monde commence par lancer le projet chez soi : `git clone -b develop …`, puis double-clic sur **`demarrer.bat`**
(Docker Desktop requis), puis `cd backend && pytest`.

### Mohamed TRIKI — socle technique et frontend (≈ 4 h)
1. **SA-9** : dépôt publié sur GitHub, CI verte ; protéger `main` ; envoyer `smartcampus-eval.zip` à Skandar.
2. **SA-16, SA-17** : `alembic upgrade head` → `downgrade base` → `upgrade head` puis `alembic check` ; capture.
3. **SA-7, SA-28, SA-29** : vérifier dans Swagger inscription, connexion, rôle réservé à l'admin, 403 d'un
   responsable IIT sur une formation ISB, conversation rattachée au compte.
4. **SA-8 — initialisation du frontend** : `npm install && npm run build`, l'application démarre ; présenter la
   structure (client API, pages Chat, Connexion, Inscription, Mon espace). Yassine prend ensuite le frontend.
5. **SA-36** : configurer le modèle choisi par Skandar, vérifier le chat de bout en bout.
6. Arbitrer les points 2 à 12 de la revue de sécurité.
7. Animer la revue (démo 5 min, tâches en *In review*, rétrospective).

### Ibrahim Ben Abdallah — conception (≈ 3 h)
1. **SA-3** : relire `docs/acteurs-processus.md` face à notre document des processus ; exporter en images les cas
   d'utilisation (PlantUML) et le diagramme d'états.
2. **SA-4** : relire `docs/architecture.md` ; exporter les diagrammes Mermaid.
3. **SA-5** : relire `docs/api.md` et vérifier qu'il correspond à Swagger.
4. **SA-12 à SA-14** : vérifier `docs/modele-donnees.md` face aux tables réelles ; noter les manques.
5. Organiser avec Mohamed la validation de la conception (30 min) ; 2 diapositives.

### Skandar Soussi — suite de l'intégration du LLM (≈ 4 h, dont 2–3 h de calcul Kaggle)
1. **SA-33 / SA-34 — en premier** : Kaggle → importer `llm-eval/kaggle_colab_eval.ipynb`, *GPU T4 x2* + Internet,
   ajouter `smartcampus-eval.zip`, *Run all* (15 modèles), récupérer `results.zip`.
2. **SA-34** : organiser la notation humaine (`*_notation_humaine.csv`, 2 notateurs par réponse).
3. **SA-33** : remplir `docs/choix-llm.md` avec les seuls chiffres mesurés ; transmettre la décision à Mohamed.
4. **SA-32** : ajouter les vraies questions de lycéens au jeu d'évaluation.
5. **SA-37, SA-38** : rejouer le dialogue avec le modèle retenu ; capture ; 1–2 diapositives.

### Yassine Koubaa — frontend, catalogue, sessions (≈ 3 h)
1. **Frontend, SA-25 / SA-26** : parcours complet dans le navigateur avec captures (chat anonyme → mémoire →
   compte → Mon espace → déconnexion → reconnexion), aussi sur mobile.
2. **SA-18, SA-20 à SA-22** : catalogue dans Swagger (24 formations, filtres, frais et conditions, 404, journal de
   synchronisation) ; relancer les tests du catalogue.
3. **ISB (réserve de SA-21)** : contacter l'ISB pour la liste des formations et les frais.
4. Corriger les défauts d'ergonomie relevés.
5. 1 diapositive « Démo ».

## 3. Planning

| Quand | Quoi | Qui |
|---|---|---|
| 21/11 matin | push GitHub et archive Kaggle | Mohamed |
| 21/11 matin | chacun clone et lance le projet ; Skandar démarre Kaggle | tous |
| 21/11 après-midi | vérifications et captures, validation de la conception, notation humaine | tous |
| 21/11 soir | PR de fin de sprint relues | Mohamed + relecteurs |
| 22/11 matin | `choix-llm.md` rempli, modèle retenu configuré | Skandar, Mohamed |
| 22/11 | revue de sprint (démo 5 min) puis rétrospective | tous |

## 4. Pistes pour le Sprint 2 (RAG)

| Membre | Piste |
|---|---|
| Mohamed TRIKI | orchestrateur LangGraph (agent « orientation »), intégration du RAG dans le backend, règles de sécurité |
| Ibrahim Ben Abdallah | conception du RAG et des agents : architecture, diagrammes, outils des agents, contrat API |
| Skandar Soussi | qualité des réponses : citation des sources, réévaluation, préparation du fine-tuning LoRA |
| Yassine Koubaa | corpus (pages officielles, PDF, données ISB), affichage des sources, tests Playwright |
