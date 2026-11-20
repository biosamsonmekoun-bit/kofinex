# KOFINEX — commandes de développement
# Deux modes de base locale :
#   make db-docker     PostgreSQL seul (docker compose) + shim Supabase
#   make db-supabase   pile Supabase complète (supabase CLI : Auth, Storage, Studio, Inbucket)

SHELL := /bin/bash
PG_DOCKER   ?= postgresql://postgres:postgres@localhost:5432/kofinex
PG_SUPABASE ?= postgresql://postgres:postgres@127.0.0.1:54322/postgres
PG_TEST     ?= postgresql://postgres:postgres@localhost:5432/kofinex_test

.PHONY: help setup db-docker db-supabase migrate test test-unit test-sql test-integration dev-api dev-web demo

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n", $$1, $$2}'

setup: ## Installe les dépendances backend et frontend
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
	cd frontend && npm install
	@test -f .env || (cp .env.example .env && echo ">> .env créé : renseignez les clés Supabase")
	@test -f frontend/.env.local || cp .env.example frontend/.env.local

db-docker: ## PostgreSQL local (docker) + migrations
	docker compose up -d postgres redis
	@until docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
	cd backend && DATABASE_URL=postgresql+psycopg://$(subst postgresql://,,$(PG_DOCKER)) .venv/bin/alembic upgrade head

db-supabase: ## Pile Supabase locale + migrations (nécessite le CLI supabase)
	supabase start
	cd backend && DATABASE_URL=postgresql+psycopg://$(subst postgresql://,,$(PG_SUPABASE)) .venv/bin/alembic upgrade head
	@echo ">> Copiez l'URL API, la clé anon, la clé service_role et le JWT secret affichés par 'supabase status' dans .env"

migrate: ## Applique les migrations sur DATABASE_URL (.env)
	cd backend && set -a && . ../.env && set +a && .venv/bin/alembic upgrade head

test: test-unit test-sql test-integration ## Tous les tests

test-unit: ## Tests unitaires Python
	cd backend && .venv/bin/pytest tests --ignore=tests/integration -q

test-sql: ## Tests RLS et Storage sur une base de test neuve
	psql "$(subst /kofinex_test,/postgres,$(PG_TEST))" -c "DROP DATABASE IF EXISTS kofinex_test" -c "CREATE DATABASE kofinex_test"
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/sql/local/00_supabase_shim.sql
	cd backend && DATABASE_URL=postgresql+psycopg://$(subst postgresql://,,$(PG_TEST)) .venv/bin/alembic upgrade head
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_rls.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_storage.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_frameworks_imports.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_financial_engine.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_management_control.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_audit_foundation.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_financial_audit.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_internal_audit.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_general_ledger.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_internal_control.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_ai.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_reporting.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_native_accounting.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_management_steering.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_fec_benin.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_statement_types.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_billing.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_third_party_collective.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_budget_chart_link.sql
	psql "$(PG_TEST)" -q -v ON_ERROR_STOP=1 -f backend/tests/sql/test_treasury_plan.sql

test-integration: ## Tests API de bout en bout (après test-sql)
	cd backend && TEST_DATABASE_URL=postgresql+psycopg://$(subst postgresql://,,$(PG_TEST)) \
	  SUPABASE_URL=http://supabase.test SUPABASE_JWT_SECRET=unused-0123456789abcdef \
	  .venv/bin/pytest tests/integration -q

dev-api: ## API sur http://localhost:8000/api/v1/docs
	cd backend && set -a && . ../.env && set +a && .venv/bin/uvicorn app.main:app --reload

dev-web: ## Frontend sur http://localhost:3000
	cd frontend && npm run dev

demo: ## Données de démonstration (DEMO_USER=<uuid>)
	@test -n "$(DEMO_USER)" || (echo "DEMO_USER=<uuid d'un utilisateur existant> requis" && exit 1)
	set -a && . ./.env && set +a && psql "$${DATABASE_URL/+psycopg/}" -v demo_user="'$(DEMO_USER)'" -f backend/scripts/seed_demo.sql
