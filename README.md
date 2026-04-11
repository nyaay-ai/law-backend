# lawyer-ai

Modular FastAPI backend for Lawyer AI.

## Project Structure

```
lawyer-ai/
├── main.py                  # FastAPI app factory
├── run.py                   # Uvicorn entry point
├── requirements.txt
├── .env.example
└── app/
    ├── core/
    │   ├── config.py        # Pydantic settings (reads .env)
    │   └── security.py      # JWT + password hashing
    ├── database/
    │   └── session.py       # SQLAlchemy engine, SessionLocal, get_db()
    ├── models/
    │   ├── base.py          # Base declarative class with audit fields
    │   └── user.py          # User ORM model
    ├── schemas/
    │   └── user.py          # Pydantic request/response schemas
    ├── services/
    │   └── user_service.py  # Business logic layer
    └── routes/
        ├── __init__.py      # Aggregates all routers → api_router
        ├── auth.py          # POST /auth/register, POST /auth/login
        └── users.py         # GET /users/{user_id}
```

## Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url> lawyer-ai && cd lawyer-ai

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env as needed

# 5. Run the server
python run.py
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/auth/register` | Register a new user |
| POST | `/api/v1/auth/login` | Login and receive JWT |
| GET | `/api/v1/users/{user_id}` | Get user by ID |

## Adding a New Feature

1. **Model** — add `app/models/your_model.py` extending `Base`
2. **Schema** — add `app/schemas/your_schema.py` with Pydantic models
3. **Service** — add `app/services/your_service.py` with business logic
4. **Route** — add `app/routes/your_route.py` with the APIRouter
5. **Register** — import and include the router in `app/routes/__init__.py`

## Database Migrations (Alembic)

```bash
alembic init alembic
# Edit alembic/env.py to import Base and set DATABASE_URL
alembic revision --autogenerate -m "initial"
alembic upgrade head
```
