# Backend FastAPI — migration DSFR

API REST qui **réutilise la logique métier existante** (`core/`, `generation/`,
`processing/`, `sessions/`) pour le nouveau frontend Vue + DSFR. Tourne **en parallèle**
de l'app Streamlit (approche strangler) — aucun code métier n'est dupliqué.

## Lancement local

Depuis la **racine du repo**, dans l'environnement qui a déjà les dépendances du projet :

```sh
pip install -r backend/requirements.txt   # ajoute fastapi/uvicorn/python-multipart
uvicorn backend.main:app --reload          # http://127.0.0.1:8000/docs
```

Le `.env` de la racine (clés LLM, modèles, DB sessions) est réutilisé tel quel.

## Endpoints (tranches migrées)

| Méthode | Route | Réutilise | Rôle |
| ------- | ----- | --------- | ---- |
| `GET`  | `/health` | — | Sonde |
| `POST` | `/documents` | `document_processor` | Upload multi-fichiers → extraction + chunking → `doc_id` |
| `POST` | `/notions/detect` | `notion_detector` | Détecte les notions d'un `doc_id` |
| `POST` | `/quiz/generate` | `quiz_generator` | Génère un QCM (niveaux, choix, notions, persona…) |
| `POST` | `/sessions` | `session_store` | Crée une session partagée à partir d'un quiz |
| `GET`  | `/sessions/{code}` | `session_store` | Vue participant (sans les bonnes réponses) |
| `POST` | `/sessions/{code}/submit` | `session_store` | Soumission + scoring serveur + corrections |

## Notes d'architecture

- Les endpoints LLM (`/notions/detect`, `/quiz/generate`) sont **synchrones** (`def`) :
  FastAPI les exécute dans un threadpool. La génération peut durer plusieurs minutes
  (voir feuille de route : passage à des jobs asynchrones + streaming SSE).
- L'état de travail du formateur (chunks d'un document) vit dans un **store mémoire**
  (`doc_store`) indexé par `doc_id`. Mono-instance pour l'instant (cf. feuille de route).
- Le scoring des sessions reste **côté serveur** (bonnes réponses jamais exposées avant
  soumission).

Voir [`../MIGRATION_DSFR.md`](../MIGRATION_DSFR.md) pour l'état d'avancement et la suite.
