# Metabase API Reference

Use this reference after the skill triggers and only when endpoint or payload detail is needed.

## Authentication

Supported credential modes:

- `METABASE_API_KEY`: sent as `X-API-Key`.
- `METABASE_SESSION_TOKEN`: sent as `X-Metabase-Session`.
- `METABASE_USERNAME` and `METABASE_PASSWORD`: exchanged through `POST /api/session`; the returned session id is used for this run only.

Credentials may be provided by environment variables or `/Users/danny/.codex/skills/metabase/.env.local`. Environment variables take precedence over `.env.local`.

Never echo these values. It is safe to say whether each variable is set.

## Common Endpoints

- `GET /api/user/current`: verify current user.
- `GET /api/search?q=...`: search Metabase objects.
- `GET /api/card/{id}`: fetch saved question metadata.
- `POST /api/card/{id}/query/json`: run a saved question and return JSON rows.
- `GET /api/dashboard/{id}`: fetch dashboard metadata and dashboard cards.
- `POST /api/dataset`: run a dataset/native query payload.
- `PUT /api/card/{id}`: update saved question metadata, including `visualization_settings`. Preserve `name`, `display`, `dataset_query`, and `collection_id` unless intentionally changing them.
- `PUT /api/dashboard/{id}`: update dashboard structure and dashcards. In Metabase `v0.61.x`, use this endpoint for adding or updating dashboard cards; older dashboard-card endpoints may return `404`.

## Native Query Payload

Use this shape for SQL passed through Metabase:

```json
{
  "database": 2,
  "type": "native",
  "native": {
    "query": "select current_date"
  },
  "parameters": []
}
```

Prefer adding an explicit SQL limit for exploratory queries. When the SQL is user-provided, do not rewrite semantics unless the user asks; ask before changing destructive-looking statements. Metabase may still reject statements based on database permissions.

## Dashboard Update Payload Notes

For dashboard card layout, visualization override, or add-card mutations, use `PUT /api/dashboard/{id}` with a `dashcards` array.

When adding a saved question to a dashboard, append a dashcard object like:

```json
{
  "id": -1,
  "card_id": 123,
  "row": 0,
  "col": 0,
  "size_x": 12,
  "size_y": 8,
  "parameter_mappings": [],
  "visualization_settings": {}
}
```

Use a negative temporary `id` that does not conflict with existing dashcards. After the `PUT`, re-fetch the dashboard and use the returned positive dashcard id for later edits.

Saved card visualization settings and dashboard-level dashcard visualization overrides are separate. If a dashboard card has override settings, updating only `PUT /api/card/{id}` may not change what the dashboard renders. Sync or update the dashcard's `visualization_settings` through `PUT /api/dashboard/{id}` when needed.

## Result Handling

- For `run-card` JSON endpoints, rows are returned as objects.
- For `/api/dataset`, Metabase commonly returns `data.cols` plus `data.rows`; convert rows to objects before analysis.
- For large results, request a small limit first, summarize schema and sample rows, then ask before expanding.

## Troubleshooting

- `401` or `403`: missing, expired, or insufficient Metabase credentials.
- `404`: wrong id, hidden object, or no permission to view it.
- `400`: invalid payload, missing database id, malformed parameters, or rejected SQL.
- Network errors: verify `METABASE_URL`, VPN, DNS, and whether the URL needs a path prefix.

When reporting failures, include only non-secret details: endpoint category, HTTP status, response message if safe, and the next action.
