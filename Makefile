# AI CCTV Analytics — common dev tasks.
# Works on macOS/Linux. On Windows, prefer the PowerShell equivalents from README.

COMPOSE ?= docker compose

.PHONY: help build up down logs ps shell-backend shell-db migrate makemigrations \
        superuser test test-backend lint seed schema clean reset

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- Docker stack ----------------------------------------------------------
build:           ## Build all images
	$(COMPOSE) build

up:              ## Start the stack in the background
	$(COMPOSE) up -d

down:            ## Stop the stack (keeps volumes)
	$(COMPOSE) down

reset:           ## Stop + WIPE DB and volumes
	$(COMPOSE) down -v

logs:            ## Tail logs for backend + workers
	$(COMPOSE) logs -f backend celery_worker celery_beat cv_worker

ps:              ## List running services
	$(COMPOSE) ps

# --- Backend shortcuts -----------------------------------------------------
shell-backend:   ## Open a shell in the backend container
	$(COMPOSE) exec backend bash

shell-db:        ## Open a psql shell on the database
	$(COMPOSE) exec db psql -U cctv -d cctv

migrate:         ## Apply Django migrations
	$(COMPOSE) exec backend python manage.py migrate

makemigrations:  ## Generate new migrations
	$(COMPOSE) exec backend python manage.py makemigrations

superuser:       ## Create a Django admin superuser
	$(COMPOSE) exec backend python manage.py createsuperuser

seed:            ## Seed dummy detection events (uses --count=100)
	$(COMPOSE) exec backend python manage.py seed_detections --count 100

schema:          ## Dump the OpenAPI schema to backend/schema.yml
	$(COMPOSE) exec backend python manage.py spectacular --file /app/schema.yml --validate

# --- Tests -----------------------------------------------------------------
test: test-backend ## Run all tests

test-backend:    ## Run Django test suite
	$(COMPOSE) exec backend python manage.py test -v 2

# --- Local-only (no Docker) -----------------------------------------------
lint:            ## Quick Python syntax check
	cd backend && python -m compileall -q apps config

clean:           ## Remove Python bytecode + Vite build artefacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf frontend/dist backend/staticfiles
