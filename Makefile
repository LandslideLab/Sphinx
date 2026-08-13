.PHONY: install test demo api mcp web build docker-up

PYTHON := .venv/bin/python
PIP := .venv/bin/pip

# ---- setup ----
install:
	python3 -m venv .venv
	$(PIP) install -e "backend[dev]" -e sdk
	cd web && npm install

# ---- testing ----
test:
	cd backend && ../$(PYTHON) -m pytest -q

# ---- demo agent (needs api+mcp running) ----
demo:
	$(PYTHON) sdk/examples/demo_agent.py --transport mcp

# ---- services ----
api:
	SPHINX_SEED_DEMO_DATA=1 $(PYTHON) -m uvicorn sphinx.main:app --host 0.0.0.0 --port 8001

mcp:
	$(PYTHON) -m sphinx.mcp.server --http --port 8100

web:
	cd web && npm run dev

# ---- web build ----
build:
	cd web && npm run build

# ---- docker ----
docker-up:
	docker compose up --build
