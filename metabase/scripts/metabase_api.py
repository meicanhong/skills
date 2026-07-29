#!/usr/bin/env python3
"""Small Metabase API helper for Codex skills."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
SKILL_DIR = Path(__file__).resolve().parents[1]
LOCAL_ENV_FILE = SKILL_DIR / ".env.local"
DATA_ANALYTICS_PALETTE = {
    "primary": "#0169cc",
    "money": "#8046d9",
    "positive": "#00692a",
    "attention": "#923b0f",
    "negative": "#ba2623",
    "neutral": "#8f8f8f",
}
DATA_ANALYTICS_COLOR_ORDER = [
    DATA_ANALYTICS_PALETTE["primary"],
    DATA_ANALYTICS_PALETTE["attention"],
    DATA_ANALYTICS_PALETTE["positive"],
    DATA_ANALYTICS_PALETTE["money"],
    DATA_ANALYTICS_PALETTE["negative"],
    "#ba437a",
    "#916f00",
    DATA_ANALYTICS_PALETTE["neutral"],
]


class MetabaseError(RuntimeError):
    pass


def load_local_env() -> None:
    if not LOCAL_ENV_FILE.exists():
        return

    for line in LOCAL_ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def base_url() -> str:
    url = env("METABASE_URL")
    if not url:
        raise MetabaseError("METABASE_URL is not set")
    return url.rstrip("/")


def request(
    method: str,
    path: str,
    *,
    body: JsonValue = None,
    query: dict[str, str] | None = None,
    token: str | None = None,
) -> Any:
    url = f"{base_url()}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    api_key = env("METABASE_API_KEY")
    session_token = token or env("METABASE_SESSION_TOKEN")
    if api_key:
        headers["X-API-Key"] = api_key
    elif session_token:
        headers["X-Metabase-Session"] = session_token

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise MetabaseError(f"HTTP {exc.code} for {method} {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise MetabaseError(f"Network error for {method} {path}: {exc.reason}") from exc

    if not raw:
        return None
    return json.loads(raw)


def login_if_needed() -> str | None:
    if env("METABASE_API_KEY") or env("METABASE_SESSION_TOKEN"):
        return None

    username = env("METABASE_USERNAME")
    password = env("METABASE_PASSWORD")
    if not username or not password:
        raise MetabaseError(
            "Set METABASE_API_KEY, METABASE_SESSION_TOKEN, or both METABASE_USERNAME and METABASE_PASSWORD"
        )

    result = request(
        "POST",
        "/api/session",
        body={"username": username, "password": password},
    )
    session_id = result.get("id") if isinstance(result, dict) else None
    if not session_id:
        raise MetabaseError("Metabase login did not return a session id")
    return str(session_id)


def dataset_rows(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    data = result.get("data")
    if not isinstance(data, dict):
        return []
    cols = data.get("cols")
    rows = data.get("rows")
    if not isinstance(cols, list) or not isinstance(rows, list):
        return []

    names: list[str] = []
    for idx, col in enumerate(cols):
        if isinstance(col, dict):
            names.append(str(col.get("name") or col.get("display_name") or f"col_{idx + 1}"))
        else:
            names.append(f"col_{idx + 1}")

    objects: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, list):
            objects.append({name: row[idx] if idx < len(row) else None for idx, name in enumerate(names)})
    return objects


def apply_limit(rows: Any, limit: int | None) -> Any:
    if limit is None or not isinstance(rows, list):
        return rows
    return rows[:limit]


def parse_json_arg(value: str) -> Any:
    if value.startswith("@"):
        path = Path(value[1:]).expanduser()
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


def deep_merge(base: Any, override: Any) -> Any:
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override

    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def card_update_body(card: dict[str, Any], visualization_settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": card["name"],
        "description": card.get("description"),
        "display": card["display"],
        "dataset_query": card["dataset_query"],
        "visualization_settings": visualization_settings,
        "collection_id": card.get("collection_id"),
    }


def dashboard_card_id(dashcard: dict[str, Any]) -> int | None:
    card_id = dashcard.get("card_id")
    if isinstance(card_id, int):
        return card_id
    card = dashcard.get("card")
    if isinstance(card, dict) and isinstance(card.get("id"), int):
        return card["id"]
    return None


def dashboard_update_body(dashcards: list[dict[str, Any]]) -> dict[str, Any]:
    return {"dashcards": dashcards}


def summarize_dashcards(dashcards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for dashcard in dashcards:
        card = dashcard.get("card") if isinstance(dashcard.get("card"), dict) else {}
        summary.append(
            {
                "dashcard_id": dashcard.get("id"),
                "card_id": dashboard_card_id(dashcard),
                "name": card.get("name"),
                "row": dashcard.get("row"),
                "col": dashcard.get("col"),
                "size_x": dashcard.get("size_x"),
                "size_y": dashcard.get("size_y"),
            }
        )
    return summary


def semantic_color_for_series(name: str) -> str:
    lowered = name.lower()
    if any(term in name for term in ("金额", "GMV", "营收", "收入", "销售额")) or any(
        term in lowered for term in ("amount", "gmv", "revenue", "sales")
    ):
        return DATA_ANALYTICS_PALETTE["money"]
    if any(term in name for term in ("触达", "复购", "成交", "成功", "可企微")) or any(
        term in lowered for term in ("reachable", "repeat", "success", "converted")
    ):
        return DATA_ANALYTICS_PALETTE["positive"]
    if any(term in name for term in ("退款", "失败", "关闭", "流失")) or any(
        term in lowered for term in ("refund", "failed", "failure", "churn")
    ):
        return DATA_ANALYTICS_PALETTE["negative"]
    if any(term in name for term in ("只下一单", "未复购", "沉睡", "机会", "占比")) or any(
        term in lowered for term in ("one_order", "dormant", "opportunity", "pct", "rate")
    ):
        return DATA_ANALYTICS_PALETTE["attention"]
    if any(term in name for term in ("平均", "客均", "人均")) or any(term in lowered for term in ("avg", "average")):
        return DATA_ANALYTICS_PALETTE["neutral"]
    return DATA_ANALYTICS_PALETTE["primary"]


def data_analytics_visualization_settings(settings: dict[str, Any]) -> dict[str, Any]:
    updated = dict(settings)
    series_settings = dict(updated.get("series_settings") or {})
    metric_names = [name for name in updated.get("graph.metrics") or [] if isinstance(name, str)]

    if metric_names:
        updated["graph.colors"] = [semantic_color_for_series(name) for name in metric_names]
        for name in metric_names:
            current = dict(series_settings.get(name) or {})
            current["color"] = semantic_color_for_series(name)
            series_settings[name] = current
    elif updated.get("graph.colors"):
        updated["graph.colors"] = DATA_ANALYTICS_COLOR_ORDER[: len(updated["graph.colors"])]
    else:
        updated["graph.colors"] = [DATA_ANALYTICS_PALETTE["primary"]]

    if series_settings:
        updated["series_settings"] = series_settings
    return updated


def merge_card_visualization_settings(card_id: int, settings: dict[str, Any], token: str | None) -> dict[str, Any]:
    card = request("GET", f"/api/card/{card_id}", token=token)
    if not isinstance(card, dict):
        raise MetabaseError(f"Card {card_id} did not return an object")
    current = card.get("visualization_settings") or {}
    if not isinstance(current, dict):
        current = {}
    merged = deep_merge(current, settings)
    request("PUT", f"/api/card/{card_id}", body=card_update_body(card, merged), token=token)
    updated = request("GET", f"/api/card/{card_id}", token=token)
    return {
        "card_id": card_id,
        "name": updated.get("name") if isinstance(updated, dict) else None,
        "display": updated.get("display") if isinstance(updated, dict) else None,
        "visualization_settings": updated.get("visualization_settings") if isinstance(updated, dict) else None,
    }


def sync_dashboard_card_settings(dashboard_id: int, token: str | None) -> dict[str, Any]:
    dashboard = request("GET", f"/api/dashboard/{dashboard_id}", token=token)
    dashcards = dashboard.get("dashcards") if isinstance(dashboard, dict) else None
    if not isinstance(dashcards, list):
        raise MetabaseError(f"Dashboard {dashboard_id} did not return dashcards")

    next_dashcards: list[dict[str, Any]] = []
    synced = 0
    for dashcard in dashcards:
        if not isinstance(dashcard, dict):
            continue
        updated_dashcard = dict(dashcard)
        card = updated_dashcard.get("card")
        if isinstance(card, dict) and isinstance(card.get("visualization_settings"), dict):
            if updated_dashcard.get("visualization_settings") != card["visualization_settings"]:
                updated_dashcard["visualization_settings"] = card["visualization_settings"]
                synced += 1
        next_dashcards.append(updated_dashcard)

    if synced:
        request("PUT", f"/api/dashboard/{dashboard_id}", body=dashboard_update_body(next_dashcards), token=token)
    verified = request("GET", f"/api/dashboard/{dashboard_id}", token=token)
    verified_dashcards = verified.get("dashcards") if isinstance(verified, dict) else []
    return {
        "dashboard_id": dashboard_id,
        "synced_dashcards": synced,
        "dashcards": summarize_dashcards(verified_dashcards if isinstance(verified_dashcards, list) else []),
    }


def add_dashboard_card(
    dashboard_id: int,
    card_id: int,
    row: int,
    col: int,
    size_x: int,
    size_y: int,
    token: str | None,
) -> dict[str, Any]:
    dashboard = request("GET", f"/api/dashboard/{dashboard_id}", token=token)
    dashcards = dashboard.get("dashcards") if isinstance(dashboard, dict) else None
    if not isinstance(dashcards, list):
        raise MetabaseError(f"Dashboard {dashboard_id} did not return dashcards")

    min_id = min((dc.get("id") for dc in dashcards if isinstance(dc, dict) and isinstance(dc.get("id"), int)), default=0)
    temp_id = min(-1, min_id - 1)
    card = request("GET", f"/api/card/{card_id}", token=token)
    settings = card.get("visualization_settings") if isinstance(card, dict) else {}
    next_dashcards = list(dashcards)
    next_dashcards.append(
        {
            "id": temp_id,
            "card_id": card_id,
            "row": row,
            "col": col,
            "size_x": size_x,
            "size_y": size_y,
            "parameter_mappings": [],
            "visualization_settings": settings if isinstance(settings, dict) else {},
        }
    )
    request("PUT", f"/api/dashboard/{dashboard_id}", body=dashboard_update_body(next_dashcards), token=token)
    verified = request("GET", f"/api/dashboard/{dashboard_id}", token=token)
    verified_dashcards = verified.get("dashcards") if isinstance(verified, dict) else []
    return {
        "dashboard_id": dashboard_id,
        "added_card_id": card_id,
        "dashcards": summarize_dashcards(verified_dashcards if isinstance(verified_dashcards, list) else []),
    }


def apply_dashboard_theme(dashboard_id: int, palette: str, token: str | None) -> dict[str, Any]:
    if palette != "data-analytics":
        raise MetabaseError(f"Unsupported palette: {palette}")

    dashboard = request("GET", f"/api/dashboard/{dashboard_id}", token=token)
    dashcards = dashboard.get("dashcards") if isinstance(dashboard, dict) else None
    if not isinstance(dashcards, list):
        raise MetabaseError(f"Dashboard {dashboard_id} did not return dashcards")

    themed_cards = 0
    next_dashcards: list[dict[str, Any]] = []
    for dashcard in dashcards:
        if not isinstance(dashcard, dict):
            continue
        updated_dashcard = dict(dashcard)
        card = updated_dashcard.get("card")
        if not isinstance(card, dict) or not isinstance(card.get("id"), int):
            next_dashcards.append(updated_dashcard)
            continue
        display = card.get("display")
        if display in {"table", "object", "action"}:
            next_dashcards.append(updated_dashcard)
            continue
        current = card.get("visualization_settings") or {}
        if not isinstance(current, dict):
            current = {}
        themed = data_analytics_visualization_settings(current)
        request("PUT", f"/api/card/{card['id']}", body=card_update_body(card, themed), token=token)
        updated_dashcard["visualization_settings"] = themed
        next_dashcards.append(updated_dashcard)
        themed_cards += 1

    if themed_cards:
        request("PUT", f"/api/dashboard/{dashboard_id}", body=dashboard_update_body(next_dashcards), token=token)
    return {
        "dashboard_id": dashboard_id,
        "palette": palette,
        "themed_cards": themed_cards,
    }


def print_table(value: Any) -> None:
    rows = value if isinstance(value, list) else [value]
    if not rows:
        print("(no rows)")
        return
    if not all(isinstance(row, dict) for row in rows):
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return

    keys: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)

    widths = {key: min(max(len(key), *(len(str(row.get(key, ""))) for row in rows)), 48) for key in keys}
    print(" | ".join(key.ljust(widths[key]) for key in keys))
    print("-+-".join("-" * widths[key] for key in keys))
    for row in rows:
        cells = []
        for key in keys:
            text = str(row.get(key, ""))
            if len(text) > widths[key]:
                text = f"{text[: widths[key] - 1]}…"
            cells.append(text.ljust(widths[key]))
        print(" | ".join(cells))


def emit(value: Any, fmt: str, limit: int | None = None) -> None:
    value = apply_limit(value, limit)
    if fmt == "json":
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        print_table(value)


def command(args: argparse.Namespace) -> Any:
    token = login_if_needed()
    if args.command == "whoami":
        return request("GET", "/api/user/current", token=token)
    if args.command == "search":
        return request("GET", "/api/search", query={"q": args.term}, token=token)
    if args.command == "card":
        return request("GET", f"/api/card/{args.id}", token=token)
    if args.command == "run-card":
        return request("POST", f"/api/card/{args.id}/query/json", token=token)
    if args.command == "dashboard":
        return request("GET", f"/api/dashboard/{args.id}", token=token)
    if args.command == "native-query":
        payload = {
            "database": args.database_id,
            "type": "native",
            "native": {"query": args.sql},
            "parameters": [],
        }
        return dataset_rows(request("POST", "/api/dataset", body=payload, token=token))
    if args.command == "update-card-viz":
        settings = parse_json_arg(args.settings_json)
        if not isinstance(settings, dict):
            raise MetabaseError("--settings-json must be a JSON object")
        return merge_card_visualization_settings(args.id, settings, token)
    if args.command == "sync-dashboard-card-settings":
        return sync_dashboard_card_settings(args.id, token)
    if args.command == "dashboard-add-card":
        return add_dashboard_card(args.dashboard_id, args.card_id, args.row, args.col, args.size_x, args.size_y, token)
    if args.command == "dashboard-theme":
        return apply_dashboard_theme(args.id, args.palette, token)
    raise MetabaseError(f"Unknown command: {args.command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Metabase API helper")
    add_output_options(parser)

    sub = parser.add_subparsers(dest="command", required=True)
    add_subparser(sub, "whoami")

    search = add_subparser(sub, "search")
    search.add_argument("term")

    card = add_subparser(sub, "card")
    card.add_argument("id", type=int)

    run_card = add_subparser(sub, "run-card")
    run_card.add_argument("id", type=int)

    dashboard = add_subparser(sub, "dashboard")
    dashboard.add_argument("id", type=int)

    native = add_subparser(sub, "native-query")
    native.add_argument("--database-id", type=int, required=True)
    native.add_argument("--sql", required=True)

    update_viz = add_subparser(sub, "update-card-viz")
    update_viz.add_argument("id", type=int)
    update_viz.add_argument("--settings-json", required=True, help="JSON object or @path to merge into visualization_settings")

    sync = add_subparser(sub, "sync-dashboard-card-settings")
    sync.add_argument("id", type=int)

    add_card = add_subparser(sub, "dashboard-add-card")
    add_card.add_argument("dashboard_id", type=int)
    add_card.add_argument("card_id", type=int)
    add_card.add_argument("--row", type=int, required=True)
    add_card.add_argument("--col", type=int, required=True)
    add_card.add_argument("--size-x", type=int, required=True)
    add_card.add_argument("--size-y", type=int, required=True)

    theme = add_subparser(sub, "dashboard-theme")
    theme.add_argument("id", type=int)
    theme.add_argument("--palette", choices=["data-analytics"], default="data-analytics")

    return parser


def add_subparser(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
) -> argparse.ArgumentParser:
    parser = sub.add_parser(name)
    add_output_options(parser)
    return parser


def add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=["json", "table"], default="json")
    parser.add_argument("--limit", type=int)


def main() -> int:
    load_local_env()
    parser = build_parser()
    args = parser.parse_args()
    try:
        emit(command(args), args.format, args.limit)
        return 0
    except MetabaseError as exc:
        print(f"metabase_api.py: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
