build:
	docker compose build

run:
	docker network create shared-net 2>/dev/null || true
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart api

logs:
	docker compose logs -f api

logs-all:
	docker compose logs -f


bash:
	docker compose exec api bash

db-shell:
	docker compose exec postgres psql -U postgres -d lawyer_ai

redis-cli:
	docker compose exec redis redis-cli -a meraredis


migrate:
	docker compose exec api alembic upgrade head

makemigrations:
	docker compose exec api alembic revision --autogenerate -m "$(msg)"

downgrade:
	docker compose exec api alembic downgrade -1

format:
	ruff format .

psql:
	docker exec -it lawyer-ai-postgres psql -U postgres lawyer_ai
