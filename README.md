# OpenProject → Mattermost webhook bridge

A small Python service that receives webhook calls from
[OpenProject](https://www.openproject.org) and reposts them as nicely
formatted Markdown messages to a
[Mattermost incoming webhook](https://docs.mattermost.com/developer/webhooks-incoming.html).

## What it does

- Listens on `POST /webhook` for OpenProject webhook payloads.
- Formats `work_package:created` and `work_package:updated` events into
  Mattermost messages with tables for the work package fields and changes.
- Description changes are shown as a unified diff in a `diff` code block, so
  Mattermost highlights added/removed lines.
- Ignores any other event types (responds `200` with `{"status": "ignored"}`).
- Optionally verifies a bearer token if OpenProject is configured to send one.

## Configuration (environment variables)

| Variable | Required | Default | Description |
|---|---|---|---|
| `MATTERMOST_WEBHOOK_URL` | yes | – | Mattermost incoming webhook URL |
| `OPENPROJECT_BASE_URL` | recommended | – | Base URL of your OpenProject instance, used to build links |
| `MATTERMOST_USERNAME` | no | `OpenProject` | Username shown in Mattermost |
| `MATTERMOST_ICON_URL` | no | OpenProject logo | Icon shown in Mattermost |
| `MATTERMOST_CHANNEL` | no | webhook default | Channel override (`town-square`) |
| `OPENPROJECT_WEBHOOK_TOKEN` | no | – | If set, requests must send `Authorization: Bearer <token>` |
| `PORT` | no | `8080` | Listen port |
| `LOG_LEVEL` | no | `INFO` | Python log level |

## Run with Docker

```bash
docker build -t openproject-mattermost-webhook .

docker run -d --name op-mm-bridge \
  -p 8080:8080 \
  -e MATTERMOST_WEBHOOK_URL="https://mattermost.example.com/hooks/xxxxx" \
  -e OPENPROJECT_BASE_URL="https://openproject.example.com" \
  openproject-mattermost-webhook
```

Or with `docker-compose.yml` (see below for the included nginx HTTPS setup):

```yaml
services:
  op-mm-bridge:
    build: .
    ports:
      - "8080:8080"
    environment:
      MATTERMOST_WEBHOOK_URL: "https://mattermost.example.com/hooks/xxxxx"
      OPENPROJECT_BASE_URL: "https://openproject.example.com"
    restart: unless-stopped
```

## HTTPS

The included `docker-compose.yml` runs an nginx reverse proxy in front of the
bridge. Place your certificate files in a `certs/` directory next to the
compose file:

```
certs/
├── fullchain.pem   # certificate (chain)
└── privkey.pem      # private key
```

Then start everything with:

```bash
docker compose up -d --build
```

nginx terminates TLS on port 443 and proxies to the bridge, while plain HTTP
on port 80 is redirected to HTTPS. Point OpenProject at
`https://<host>/webhook`.

For a quick self-signed certificate (fine for internal/testing setups):

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:4096 -nodes -days 365 \
  -keyout certs/privkey.pem -out certs/fullchain.pem \
  -subj "/CN=your-hostname"
```

To use your own proxy instead, run the bridge container without published
ports (or behind your existing proxy) and forward to its internal port 8080.
The `certs/` directory is git-ignored; never commit private keys.

## Configure OpenProject

1. In OpenProject: **Administration → Webhooks → New webhook**.
2. Set the payload URL to `http://<host>:8080/webhook`
   (add an `Authorization: Bearer <token>` header and set
   `OPENPROJECT_WEBHOOK_TOKEN` to the same value if you want authentication).
3. Select the work package events you want to receive.
4. Save; OpenProject will send a test payload which the bridge ignores
   gracefully.

## Endpoints

- `POST /webhook` — receives OpenProject webhooks.
- `GET /health` — health check.

## Development

```bash
pip install -r requirements.txt
MATTERMOST_WEBHOOK_URL=... python app.py
```

Test locally:

```bash
curl -X POST http://localhost:8080/webhook \
  -H 'Content-Type: application/json' \
  -d '{"action":"work_package:created","actor":{"name":"Jane Doe"},"work_package":{"id":42,"subject":"Fix the thing","project":{"name":"My Project"},"type":{"name":"Bug"},"status":{"name":"New"},"priority":{"name":"Normal"},"assignee":{"name":"John"},"author":{"name":"Jane Doe"},"description":{"raw":"Something broke."}}}'
```
