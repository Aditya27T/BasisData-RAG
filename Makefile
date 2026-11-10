.PHONY: api webui

api:
	uv run uvicorn app.web_api:app --host 127.0.0.1 --port 8000 --reload

webui:
	@test -d webui/node_modules || npm --prefix webui install
	@set -e; \
	uv run uvicorn app.web_api:app --host 127.0.0.1 --port 8000 & api_pid=$$!; \
	trap 'kill $$api_pid 2>/dev/null || true; wait $$api_pid 2>/dev/null || true' EXIT INT TERM; \
	attempt=0; \
	until curl -fsS http://127.0.0.1:8000/api/health >/dev/null; do \
		kill -0 $$api_pid || exit 1; \
		attempt=$$((attempt + 1)); \
		test $$attempt -lt 60 || exit 1; \
		sleep 1; \
	done; \
	npm --prefix webui run dev -- --host 127.0.0.1
