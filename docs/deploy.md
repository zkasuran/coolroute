# Deploying the demo

The web UI (`web/app.py`) is a small FastAPI app. It ships ready to run on the
labelled **mock** backend, so a public demo needs no FortyGuard key. Point it at
the live API and turn on the agent later with runtime environment only. No
secrets live in the image or the repo.

## Runtime environment

| Variable | Needed when | Notes |
| --- | --- | --- |
| `FORTYGUARD_BACKEND` | always | `mock` (default) or `live`. |
| `FORTYGUARD_API_KEY` | `live` only | The emailed key. Leave unset on mock. |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | to enable `POST /api/ask` | The reasoning model. Without them `/api/ask` returns 503; the deterministic route and time endpoints still work. |
| `COOLROUTE_WEB_KEY` | any public exposure | Requires an `x-api-key` header on the planning endpoints. See Security. |
| `PORT` | some hosts | Injected by Fly / Render / Cloud Run. Defaults to 8000. |

## Security

The server has **no authentication by default** and logs a warning when it runs
open. It only reads heat data and performs no writes, so the blast radius is low,
but do not expose it public and open:

- Set `COOLROUTE_WEB_KEY` to a random string. Clients then send `x-api-key`.
- Only set the `OPENAI_*` variables if you want `/api/ask` live. Those endpoints
  spend real model budget per call, so gate them behind `COOLROUTE_WEB_KEY` and
  do not hand the URL out ungated.

## Build and run with Docker

```bash
docker build -t coolroute .

# mock demo, protected:
docker run --rm -p 8000:8000 -e COOLROUTE_WEB_KEY=$(openssl rand -hex 16) coolroute

# smoke it:
curl -s localhost:8000/health
curl -s -X POST localhost:8000/api/time -H "x-api-key: <the key you set>"
```

## Put it on a public URL

Any container host works because the image reads all config from the environment.

- **A VM or EC2 with Docker.** `docker run -d --restart=unless-stopped -p 80:8000
  -e COOLROUTE_WEB_KEY=... coolroute`, then front it with the box's public DNS or
  a reverse proxy for TLS.
- **A container PaaS (Fly.io, Render, Cloud Run).** Deploy from this Dockerfile
  and set the variables above as the platform's secrets. These inject `$PORT`,
  which the image already honours.

Verify the deployed URL resolves **anonymously** (log out or `curl` with no
cookies) before citing it in the submission.

## Going live

When the FortyGuard key lands, set `FORTYGUARD_BACKEND=live` and
`FORTYGUARD_API_KEY=<key>` in the host environment and redeploy. Nothing above the
adapter changes and the mock demo URL becomes the live demo URL.
