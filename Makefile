.PHONY: up down logs seed attack restore fault clear test demo ps build dashboard dashboard-api frontend-build

dashboard:
	@echo "Demo console (FastAPI + React) at http://localhost:8090 (Ctrl-C to stop)"
	python3 dashboard/api.py --port 8090

dashboard-legacy:
	@echo "Legacy stdlib console at http://localhost:8090 (Ctrl-C to stop)"
	python3 dashboard/app.py 8090

frontend-build:
	cd dashboard/frontend && npm run build


# NOTE (WSL): if `make build` fails with "error getting credentials", run:
#   mkdir -p /tmp/dockercfg && echo '{}' > /tmp/dockercfg/config.json
#   DOCKER_CONFIG=/tmp/dockercfg docker compose build
# (Docker Desktop's credsStore helper is flaky inside WSL; empty config
# suffices for public pulls.)

up:
	docker compose --env-file .env up -d
	@echo "Waiting for storage health..."
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12; do curl -sf http://localhost:9000/minio/health/live && break || sleep 5; done
	docker compose ps

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs --tail=100 -f

ps:
	docker compose ps

seed:
	docker compose exec app-server-1 python3 -m lab.cli seed --count 300
	docker compose exec app-server-2 python3 -m lab.cli seed --count 300

attack:
	docker compose exec app-server-1 python3 -m lab.cli attack run --rate 15

restore:
	docker compose exec app-server-1 python3 -m lab.cli restore --latest-clean --host app-server-1

fault:
	docker compose exec app-server-1 python3 -m lab.cli fault inject $(NAME)

clear:
	docker compose exec app-server-1 python3 -m lab.cli fault clear --all

test:
	PYTHONPATH=src python3 -m pytest tests/ -v

demo:
	bash scripts/demo.sh
