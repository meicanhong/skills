---
name: metabase
description: Use when the user asks to inspect Metabase, query Metabase cards or dashboards, run a Metabase SQL/native query, fetch BI data, analyze saved questions, diagnose Metabase API access, or turn Metabase results into reports. Trigger phrases include metabase, Metabase card, Metabase dashboard, saved question, question id, dashboard id, BI query, BI report, and Metabase API.
metadata:
  short-description: Query and inspect Metabase data safely
---

# Metabase

Use this skill to perform Metabase work through the REST API. Prefer the bundled script for authentication, card/dashboard lookup, query execution, and explicitly requested dashboard/card updates instead of rewriting HTTP calls.

## Safety Defaults

- Treat Metabase as a production analytics system unless the user says otherwise.
- Default to read-only operations: list, fetch, query, export, summarize, and diagnose access.
- Do not create, update, archive, delete, or move Metabase objects unless the user explicitly requests that exact mutation.
- Do not print credentials, session tokens, API keys, cookies, or raw connection strings.
- When results may contain sensitive customer or financial data, summarize by default and only show raw rows when the user asks.
- For dashboard/card mutations, fetch the current object first, make the smallest necessary change, preserve SQL/query payloads, layout, parameters, and existing visualization settings that are not part of the request, then fetch again to verify.

## Setup

Credentials can come from process environment variables or from the local private config file at `/Users/danny/.codex/skills/metabase/.env.local`.

- `METABASE_URL`: base URL, for example `https://metabase.example.com`
- One of:
  - `METABASE_API_KEY`
  - `METABASE_SESSION_TOKEN`
  - `METABASE_USERNAME` and `METABASE_PASSWORD`

Prefer environment variables for temporary overrides. The bundled script loads `.env.local` automatically when environment variables are absent. Never print `.env.local`.

Read [references/metabase-api.md](references/metabase-api.md) when you need endpoint details, query payload shape, or troubleshooting guidance.

Read [references/metabase-dashboard-build.md](references/metabase-dashboard-build.md) when the user asks to create, substantially revise, extend, or polish a Metabase dashboard. This reference adapts the Data Analytics dashboard-building workflow to Metabase cards, SQL, layout, visualization settings, and QA.

## Workflow

1. Confirm the user's target: card id, dashboard id, SQL/native query, collection/search term, or access diagnosis.
2. Check whether the required Metabase environment variables are present without printing secret values.
3. For dashboard-building tasks, define the dashboard brief, metric model, source path, layout order, and QA plan before creating many cards. Use `references/metabase-dashboard-build.md` for the Metabase-specific pattern.
4. Use `scripts/metabase_api.py` for API operations:
   - `whoami`: verify authentication.
   - `card <id>`: inspect a saved question.
   - `run-card <id>`: run a saved question and return JSON rows.
   - `dashboard <id>`: inspect dashboard metadata and cards.
   - `search <term>`: find cards, dashboards, collections, and other Metabase objects.
   - `native-query --database-id <id> --sql <sql>`: run a native SQL query through Metabase.
   - `update-card-viz <id> --settings-json ...`: merge visualization settings into a saved question.
   - `sync-dashboard-card-settings <dashboard_id>`: copy each saved card's visualization settings onto its dashboard card override.
   - `dashboard-add-card <dashboard_id> <card_id> --row --col --size-x --size-y`: add a saved question to a dashboard using the dashboard update endpoint.
   - `dashboard-theme <dashboard_id> --palette data-analytics`: apply a consistent Data Analytics chart palette to chart-like cards.
5. For analysis tasks, preserve the exact query/card/dashboard ids in the answer, state filters or limits used, and distinguish observed results from interpretation.
6. If API access fails, report the exact non-secret failure: HTTP status, endpoint category, and likely fix.

## Mutation Notes

Only mutate when the user explicitly asks to create, update, style, move, or otherwise change a Metabase object. Before mutating, get the current card or dashboard state and update only the requested fields.

For Metabase `v0.61.x`, prefer `PUT /api/dashboard/{id}` with a `dashcards` array for dashboard card changes. Older endpoint patterns such as `POST /api/dashboard/{id}/cards` may return `404` even for valid dashboards. When adding a dashcard through `PUT /api/dashboard/{id}`, use a negative temporary `id` for the new dashcard and include its `card_id`, `row`, `col`, `size_x`, and `size_y`.

When changing visualization settings:

- Preserve `dataset_query`, `display`, `collection_id`, and existing card metadata unless the user asked to change them.
- Merge new `visualization_settings` into the existing settings instead of replacing the whole object.
- Preserve `column_settings`, especially percentage formats such as `number_style: "percent"`.
- If dashboard-level dashcard overrides exist, update or sync those too; otherwise the dashboard can keep showing stale colors/field mappings even after the saved card is changed.
- After changes, re-fetch the card/dashboard and summarize card ids, display types, colors/field settings, and any remaining rendering risk.

## Dashboard Styling Defaults

When the user asks to unify dashboard colors and does not specify a palette, use the Data Analytics chart palette:

- Primary volume/customer/order counts: `#0169cc`
- Money, GMV, and value metrics: `#8046d9`
- Reachable, repeat, success, or positive metrics: `#00692a`
- Opportunity, one-order, dormant, or attention metrics: `#923b0f`
- Refund, failure, or negative guardrails: `#ba2623`
- Neutral/supporting metrics: `#8f8f8f`

Prefer semantic consistency over making every chart use a different color. Use Metabase native settings such as `graph.colors`, `series_settings`, `graph.dimensions`, `graph.metrics`, and `column_settings` rather than changing SQL only to affect presentation.

## Dashboard QA Checklist

Before handing off a dashboard mutation:

- The dashboard opens from `GET /api/dashboard/{id}` and every changed card id is present.
- Cards with chart displays have the needed dimensions and metrics.
- Percent fields use percent formatting in both card settings and dashboard dashcard overrides when overrides are present.
- Saved card settings and dashcard override settings are synchronized when needed.
- Layout positions and sizes are preserved unless the user requested a layout change.
- SQL and source database ids were not altered by styling-only changes.

## Commands

Run from any working directory:

```bash
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py whoami
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py search "revenue"
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py card 123
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py run-card 123 --limit 100
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py dashboard 45
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py native-query --database-id 2 --sql "select current_date"
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py update-card-viz 123 --settings-json '{"graph.colors":["#0169cc"]}'
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py sync-dashboard-card-settings 45
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py dashboard-add-card 45 123 --row 0 --col 0 --size-x 12 --size-y 8
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py dashboard-theme 45 --palette data-analytics
```

Use `--format table` for quick previews and `--format json` for downstream processing.
