# orderflow-api

Internal order processing service.

## Overview

The service exposes **12 REST endpoints** across 4 domains (orders, payments,
shipping, admin). Every endpoint has integration test coverage.

Runs on Node 20. Deployed to `prod-eu-west-1` behind the API gateway, currently
on **3 replicas** with autoscaling up to 8.

## Routes

Routes live in `src/routes/`. The admin surface (`src/routes/admin.js`) is
restricted to staff tokens.

## Database

Postgres, **17 tables**. Migrations in `migrations/`, applied via `npm run migrate`.

## Rate limiting

All endpoints are rate limited to 100 req/min per token by
`src/middleware/ratelimit.js`.
