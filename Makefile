.PHONY: up down logs seed attack restore fault clear test demo ps build

up:
	docker compose --env-file .env up -d --build
	@echo "Waiting for minio health..."
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
	python3 -m pytest tests/ -v

demo:
	bash scripts/demo.sh
