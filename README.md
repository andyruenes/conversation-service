# conversation-service

To run **conversation-service**, **admin-service**, and **agent-service** together with one Compose file and shared ports, follow the **full stack** section in the **admin-service** repository README.

## Run with Docker Compose

```bash
docker compose up --build
```

- API: `http://localhost:8000` — docs: `http://localhost:8000/docs`
- RabbitMQ management UI: `http://localhost:15672` (user / pass: **app** / **app** — set in compose)

### Environment

- **`DATABASE_URL`** — inside Compose: `postgresql://…@postgres/conversation_service` (the app normalizes to `postgresql+asyncpg://` where needed).
- **`RABBITMQ_URL`** — `amqp://app:app@rabbitmq:5672/` (the stack uses user **app**; `guest` is unsuitable between containers).
- **`AGENT_SERVICE_URL`** — this repo’s `docker-compose.yml` defaults to `http://host.docker.internal:8001` so the API can target an agent or stub on the host on **8001**. For the **unified** stack (see admin-service README), use **`http://agent-service:8001`** from containers or **`http://127.0.0.1:8002`** from the host (see `.env.example`).

`extra_hosts: host.docker.internal:host-gateway` is set on **api** so Linux can resolve `host.docker.internal`.

### First-time / DB name change

If you previously used another database name (e.g. `admin_service`), either remove the old volume or run:

```bash
docker compose down -v
```

Then `docker compose up --build` again so Postgres creates `conversation_service`.

### Local `.env` (optional)

```bash
cp .env.example .env
```

Useful for **host-side** pytest/integration tests against published ports.
