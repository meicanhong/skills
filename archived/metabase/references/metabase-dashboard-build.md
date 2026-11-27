# Metabase Dashboard Build Workflow

Use this reference when creating, extending, redesigning, or polishing a Metabase dashboard. It adapts the Data Analytics dashboard-building workflow to Metabase's saved questions, native SQL cards, dashboard layout, visualization settings, and API constraints.

## Dashboard Intent

A good Metabase dashboard should be summary-first, chart-led, scannable, and useful before the viewer interacts. It should answer the audience's main question at the top, then explain movement, drivers, segments, risks, and follow-up detail lower down.

Before creating many cards, decide:

- Audience: who will use this dashboard and what action or operating review it supports.
- Measurement object: what entity is being monitored, such as customers, orders, revenue, campaigns, sales follow-up, product usage, or data quality.
- Time anchor: current period, latest complete day, comparison window, campaign year, cohort definition, or other business date boundary.
- Source path: authoritative tables, saved questions, dashboards, or warehouse views. Verify with live queries when metrics depend on data.
- Refresh expectation: whether cards can use production tables/views directly or need a modeled aggregate/MV first.

Ask only when a missing answer would materially change the dashboard. Otherwise state a reasonable assumption and build.

## Metric Model

Do not start from a fixed checklist. Classify the measurement object and choose a balanced metric model. Use these families as prompts:

- Reach: eligible population, coverage, penetration, touchable users, activation.
- Volume: events, orders, customers, sessions, tasks, messages, throughput.
- Value: GMV, revenue, cost, margin, LTV, savings, productivity.
- Quality: success, refund, failure, latency, data coverage, satisfaction, correctness.
- Depth: repeat behavior, order count, intensity, lifecycle stage, maturity.
- Mix: channel, segment, product, salesperson, cohort, geography, customer type.
- Movement: trend, growth, seasonality, pre/post change, latest versus prior.
- Risk and constraints: dormant value, unreachable users, refunds, anomalies, missing data.

Map chosen metrics into dashboard roles:

- Hero metrics: 3 to 6 top-level KPIs that define status.
- Movement: 1 to 3 trend cards showing recent direction.
- Diagnosis: grouped charts that explain where the metric comes from.
- Guardrails: quality or risk cards that stop misinterpretation.
- Detail: tables for lookup, follow-up, or operational export.

Keep metric definitions consistent across cards. Reuse the same date filters, non-refund logic, customer identity, and join rules unless intentionally comparing definitions.

## Layout Pattern

Use this default structure unless the user or existing dashboard has a stronger convention:

1. Hero KPI row: compact scalar cards for current status and major denominators.
2. Trend row: primary movement over time, ideally full-width.
3. Funnel or coverage row: conversion, reachability, activation, or lifecycle progression.
4. Segmentation rows: value bands, order count bands, product/category mix, salesperson or channel rankings.
5. Opportunity/risk rows: dormant value, one-order customers, refunds, unreachable customers, low-repeat cohorts.
6. Detail tables: candidate lists, Top-N products/customers/sales owners, rule definitions, exceptions.

Put cards that answer the same business question next to each other. Keep detail tables lower on the page. Do not make the top of a dashboard a wall of tables.

## Chart Selection

Pick the simplest chart that answers the question:

- `scalar`: one KPI, especially denominators and top-line totals.
- `line`: movement over time with a date on the x-axis.
- `bar`: category comparison with a short category list.
- `row`: horizontal ranking or funnel-like stage comparison, especially when labels are long.
- `funnel`: use only when Metabase can map the stage and metric fields correctly; otherwise use `row`.
- `table`: lookup, export, rule detail, or Top-N detail after charts have framed the story.

Avoid mixing unrelated metrics in one chart. If a chart has both money and counts, confirm the visual scale is still readable; otherwise split it or make the money metric a separate card.

For percentages, return decimal ratios from SQL, such as `0.4584`, and set Metabase `column_settings` to `number_style: "percent"` with a small number of decimals.

## SQL And Data Rules

Use durable production tables/views/MVs for final dashboards. Avoid scratch tables unless the user explicitly asked for a prototype.

For each SQL card:

- Use human-readable aliases in the final `SELECT`, because Metabase uses them in labels and settings.
- Add explicit sort columns for buckets, then hide or omit them from the final visible output when possible.
- Keep filters and business rules visible in the SQL: date range, paid order rule, refund rule, closed order rule, identity key, dedup grain.
- Query at the card's display grain. Do not return raw detail rows for a chart that needs only aggregates.
- Limit ranking/detail cards to a sane Top-N unless the user needs export.
- For exploratory work, first run a small query or count before creating many expensive cards.

When a table or view is slow, inspect whether a materialized view or modeled aggregate is appropriate before building a dashboard that depends on repeated heavy queries.

## Metabase Build Sequence

Use the helper where possible:

```bash
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py whoami
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py native-query --database-id 2 --sql "select current_date"
python /Users/danny/.codex/skills/metabase/scripts/metabase_api.py dashboard 45
```

For a new or expanded dashboard:

1. Verify auth and target database/dashboard access.
2. Run source validation queries for the metric denominators and key joins.
3. Create or update saved question cards with native SQL.
4. Add cards to the dashboard using `PUT /api/dashboard/{id}` or the helper's `dashboard-add-card`.
5. Set visualization settings on each card: `graph.dimensions`, `graph.metrics`, `graph.colors`, `series_settings`, `column_settings`, titles, legends, and value labels.
6. Sync dashboard-level dashcard overrides after changing saved card visualization settings.
7. Re-fetch the dashboard and summarize card ids, layout, display type, and any caveats.

For Metabase `v0.61.x`, dashboard card updates should use `PUT /api/dashboard/{id}` with a `dashcards` array. Older add-card endpoints may return `404`.

## Visual Style

When no project-specific palette exists, use the Data Analytics palette and keep semantics stable:

- Counts, customers, orders, and primary volume: `#0169cc`
- Money, GMV, revenue, value: `#8046d9`
- Reachable, repeat, success, positive action: `#00692a`
- Opportunity, dormant, one-order, attention: `#923b0f`
- Refund, failure, negative guardrail: `#ba2623`
- Neutral/supporting metric: `#8f8f8f`

Apply colors through Metabase settings rather than SQL. Prefer consistent semantic colors across the whole dashboard over decorative variety.

Use short card titles. Put metric definitions in card descriptions or handoff text, not in overly long chart titles.

## Metabase QA

Before handoff:

- Fetch the dashboard and confirm every intended card id is present.
- Run or inspect important cards, especially new SQL and expensive joins.
- Confirm cards have dimensions and metrics that match their display type.
- Confirm percentages render as percentages, not raw decimals.
- Confirm saved card visualization settings and dashboard dashcard overrides are aligned.
- Confirm the layout starts with hero metrics, then trend, then diagnosis, then detail.
- Confirm SQL definitions reconcile across related cards.
- Confirm sensitive detail rows are summarized unless the user requested raw data.
- Report dashboard URL, changed card ids, validation performed, and remaining caveats.

## Handoff

A good handoff is concise:

- Dashboard link.
- What was created or changed.
- Source tables and key filters.
- Validation performed.
- Known caveats or follow-up ideas.

Do not end with a vague "go look at it". Give the user the exact dashboard URL and the high-signal summary of what changed.
