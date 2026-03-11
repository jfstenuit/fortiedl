# =============================================================================
# Blocklist Manager — developer convenience targets
# =============================================================================
# Requirements: sudo docker, Python venv at .venv/
# =============================================================================

.PHONY: dev prod stop down logs test help

COMPOSE     := sudo docker compose
COMPOSE_DEV := sudo docker compose -f docker-compose.yml -f docker-compose.dev.yml

# Default target
.DEFAULT_GOAL := help

# ── Development ───────────────────────────────────────────────────────────────
# Starts the database and reverse proxy in Docker, then launches Flask's
# built-in debug server on the host (port 5000, hot-reload enabled).
# nginx proxies HTTPS → http://localhost:5000 via host.docker.internal.
dev: .env nginx/certs/cert.pem  ## Start DB + proxy (Docker) and Flask debug server (host)
	$(COMPOSE_DEV) up -d db proxy
	@printf 'Waiting for database'; \
	 until $(COMPOSE_DEV) exec -T db pg_isready -q 2>/dev/null; do printf '.'; sleep 1; done; \
	 echo ' ready'
	DB_HOST=localhost .venv/bin/flask --app wsgi:app run --debug --port 5000

# ── Production ────────────────────────────────────────────────────────────────
# Builds the application image and starts the full stack (db + app + proxy).
prod: .env nginx/certs/cert.pem  ## Build image and start full containerised stack
	$(COMPOSE) up -d --build

# ── Helpers ───────────────────────────────────────────────────────────────────
stop: ## Stop and remove all containers (data volume preserved)
	$(COMPOSE) down

logs: ## Follow logs for all running containers
	$(COMPOSE) logs -f

test: ## Run the automated test suite (starts its own DB container)
	bash run-tests.sh

# ── Guards ────────────────────────────────────────────────────────────────────
.env:
	@echo ""
	@echo "  ERROR: .env not found."
	@echo "  Create it from the template and fill in all values:"
	@echo ""
	@echo "      cp .env.example .env"
	@echo ""
	@false

nginx/certs/cert.pem:
	@echo "No TLS certificate found — generating a self-signed certificate for dev/test."
	@echo "For production, replace nginx/certs/cert.pem and nginx/certs/privkey.pem"
	@echo "with your real certificate before running 'make prod'."
	@echo ""
	bash nginx/gen-cert.sh

# ── Help ──────────────────────────────────────────────────────────────────────
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'
