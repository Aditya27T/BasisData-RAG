.PHONY: api webui

export UV_LINK_MODE := copy

api:
	uv run uvicorn app.web_api:app --host 127.0.0.1 --port 8000 --reload

webui:
	@test -d webui/node_modules || npm --prefix webui install
	@curl -fsS http://127.0.0.1:8000/api/health >/dev/null || { \
		echo "API belum jalan. Jalankan 'make api' di terminal lain, lalu 'make webui'."; \
		exit 1; \
	}
	npm --prefix webui run dev -- --host 127.0.0.1
