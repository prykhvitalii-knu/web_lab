# Akatosh Beer Recipe Book

Akatosh is a multi-tenant recipe-book application built for the Web Technologies lab. It demonstrates a Python/FastAPI backend, a browser interface, authenticated JSON APIs, asynchronous jobs, caching, automated tests, and an AWS-hosted architecture.

The project is organized around three layers:

- **Browser:** a Bootstrap interface for signing in, managing recipes and ingredients, and attaching files.
- **Application:** FastAPI routes and Pydantic schemas call SQLAlchemy models and CRUD helpers.
- **Infrastructure:** the hosted application runs on AWS. Docker Compose provides a separate local environment for the API, database, cache, queue, and worker.

## Architecture

```text
Browser
  ├── Website ── CloudFront ── private S3 bucket (frontend)
  └── API calls ── API Gateway ── Lambda (FastAPI, private VPC subnets)
                                      ├── private RDS PostgreSQL
                                      ├── private S3 bucket (recipe uploads)
                                      ├── Secrets Manager
                                      └── NAT Gateway for outbound integrations

Local Docker Compose demo (separate from AWS production stack):
  FastAPI + PostgreSQL + Redis + RabbitMQ + Celery worker
```

The static website bucket and upload bucket block public access. CloudFront reads the website bucket through Origin Access Control. The API runs on Lambda behind API Gateway; Lambda connects to a non-public RDS database in private subnets. The NAT Gateway provides outbound access for integrations. Runtime secrets are retrieved from AWS Secrets Manager.

RabbitMQ, Redis, Celery, Telegram notifications, and MCP are demonstrated in the local Compose environment. The assistant starts an MCP stdio client for the authenticated tenant and exposes read-only recipe tools to Gemini; the hosted AWS assistant does not start MCP. The live site is [akatosh.local-domain.party](https://akatosh.local-domain.party); the API's interactive documentation is at [api.akatosh.local-domain.party/docs](https://api.akatosh.local-domain.party/docs).

Browser sign-in uses an HttpOnly JWT cookie, so refreshes restore the session without exposing the token to JavaScript. Cookie-authenticated writes require a CSRF token; Bearer-token API clients remain supported.

## Lab points and where to find them

| Point | Demonstration | Implementation |
|---|---|---|
| **C1 — MVC architecture** | User, recipe, and ingredient models; schemas; CRUD helpers; recipe file uploads. | `app/models.py`, `app/schemas.py`, `app/crud.py`, `app/main.py` |
| **C5 — REST API** | JSON create, list, read, update, and delete endpoints with HTTP status codes. | `app/main.py` (`/api/recipes/` routes) |
| **B1 — Pagination API** | `skip` and `limit` query parameters with `total` and `next_link` in the response. | `app/main.py` (`GET /api/recipes/`), `app/schemas.py` |
| **C16 — Authentication and authorization** | Registration, password verification, JWT Bearer authentication, and Google OAuth sign-in. | `app/auth.py`, `app/main.py` |
| **C4 — Containerization** | Single-stage non-root Docker image and a multi-container local stack. | `Dockerfile`, `docker-compose.yml` |
| **B9 — API caching** | Redis caches the paginated `/recipes/` response for 60 seconds; recipe writes invalidate the cache. | `app/main.py` |
| **B6 — Feature flags** | Read tenant flags and update allowed flags through an admin-protected endpoint. | `app/main.py`, `app/crud.py`, `app/models.py` |
| **B5 — Tenant isolation** | Recipe access is scoped to the tenant belonging to the authenticated user. | `app/main.py`, `app/crud.py`, `app/models.py` |
| **B8 — Message queue** | Celery dispatches background work through RabbitMQ to a separate worker. | `app/main.py`, `app/worker.py`, `docker-compose.yml` |
| **B2 — Telegram integration** | Local recipes can notify through Celery; the hosted API sends a Telegram message after JSON recipe creation when bot configuration is supplied. | `app/worker.py`, `app/telegram.py`, `app/main.py` |
| **QA1 — Automated API testing** | Pytest coverage for API behavior, browser flow, and MCP tools. | `tests/test_api.py`, `tests/test_e2e.py`, `tests/test_mcp.py` |
| **QA2 — E2E testing and coverage** | The browser test covers mobile layout/SEO metadata, account registration and sign-out, plus recipe create, edit, and delete. CI prints Python application line coverage and uploads an HTML report; it does not instrument frontend JavaScript. | `tests/test_e2e.py`, CI coverage artifact |
| **QA3 — Authentication testing** | Registration/login, protected routes, and Google OAuth callback tests. | `tests/test_api.py` |
| **C6 — Bootstrap UI** | Responsive recipe-book interface with an accessible Bootstrap modal for each tenant's recipe details. | `frontend/index.html`, `frontend/assets/app.js`, `frontend/assets/site.css` |
| **C19 — Static content on AWS S3** | Static frontend assets are stored in S3 and delivered through CloudFront. | `terraform/main.tf`, `frontend/` |
| **C7 — SEO** | The public homepage has an absolute canonical and social URL; `robots.txt` points to an absolute sitemap. Private tenant recipes are intentionally excluded. Automated tests validate the generated files, but Search Console indexing still needs external verification. | `app/seo.py`, `scripts/publish_static_site.py`, `frontend/` |
| **C21 — AI agent** | Gemini streams answers and visible progress updates, including when a tenant-scoped MCP recipe tool is called. | `app/main.py`, `frontend/assets/app.js` |
| **C22 — MCP integration** | The local assistant connects to the MCP server over stdio and can call its read-only recipe tools; recipe creation remains an explicit MCP operation. | `app/mcp_agent.py`, `app/mcp_server.py`, `docker-compose.yml` |


### Video 3 — AWS architecture and static hosting

1. Trace the browser request: CloudFront serves the static frontend from the private S3 origin (**C19**).
2. Trace an API request: API Gateway invokes Lambda, which accesses private RDS and the private uploads bucket.
3. Show the VPC's public/private subnets, Lambda-to-RDS security boundary, NAT egress, and Secrets Manager role in the architecture.
4. Briefly show the Terraform resource definitions that describe the hosted network, compute, database, storage, and access boundaries.
5. Revisit the live site and API docs to connect the hosted application to the earlier feature demonstrations.

## Tests

Run the mandatory unit tests separately:

```sh
python -m pytest tests/unit -q
```

Run the complete test suite:

```sh
python -m pytest -q
```

## Repository map

```text
app/                    FastAPI application, models, schemas, CRUD, auth, worker, MCP server
frontend/               Bootstrap static website and browser behavior
tests/unit/              Isolated unit tests
tests/                  API, end-to-end browser, and MCP tests
terraform/               AWS application infrastructure and state bootstrap
lambda/                  Lambda handler and packaging script
scripts/                 Supporting AWS configuration/publishing helpers
Dockerfile               Non-root application image
docker-compose.yml       Local multi-service demonstration stack
.github/workflows/       Automated test and build checks
```
