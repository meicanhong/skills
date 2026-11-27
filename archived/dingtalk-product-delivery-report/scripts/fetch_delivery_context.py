#!/usr/bin/env python3
"""Fetch DingTalk project-table and work-log context without mutating data."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = SCRIPT_DIR.parent / "references" / "default-scope.json"
DEFAULT_CREDENTIALS = SCRIPT_DIR / ".env"


class DingTalkError(RuntimeError):
    """A sanitized DingTalk API error."""


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"凭证文件第 {line_number} 行缺少 '='")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_credentials(path: Path | None) -> tuple[str, str]:
    values = parse_env_file(path) if path else {}
    for key in (
        "DWS_CLIENT_ID",
        "DWS_CLIENT_SECRET",
        "DINGTALK_APP_KEY",
        "DINGTALK_APP_SECRET",
    ):
        if os.environ.get(key):
            values[key] = os.environ[key]

    client_id = values.get("DWS_CLIENT_ID") or values.get("DINGTALK_APP_KEY")
    client_secret = values.get("DWS_CLIENT_SECRET") or values.get(
        "DINGTALK_APP_SECRET"
    )
    if not client_id or not client_secret:
        raise ValueError(
            "缺少钉钉应用凭证；请设置 DWS_CLIENT_ID/DWS_CLIENT_SECRET，"
            "传入 --credentials-file，或创建 scripts/.env"
        )
    return client_id, client_secret


def resolve_credentials_path(explicit_path: Path | None) -> Path | None:
    if explicit_path is not None:
        return explicit_path
    return DEFAULT_CREDENTIALS if DEFAULT_CREDENTIALS.is_file() else None


def _api_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "钉钉返回了无法识别的响应"
    code = payload.get("errcode", payload.get("code"))
    message = payload.get("errmsg", payload.get("message", "未知错误"))
    return f"钉钉 API 错误 code={code}: {message}"


@dataclass
class HttpClient:
    timeout: float = 30.0

    def request_json(
        self,
        method: str,
        endpoint: str,
        *,
        query: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        form_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = endpoint
        if query:
            url = f"{endpoint}?{urllib.parse.urlencode(query)}"

        body: bytes | None = None
        request_headers = dict(headers or {})
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        elif form_body is not None:
            body = urllib.parse.urlencode(form_body).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"

        request = urllib.request.Request(
            url, data=body, headers=request_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                detail = _api_message(payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                detail = f"HTTP {exc.code}"
            raise DingTalkError(detail) from None
        except urllib.error.URLError as exc:
            raise DingTalkError(f"钉钉网络请求失败: {exc.reason}") from None
        except json.JSONDecodeError:
            raise DingTalkError("钉钉返回了非 JSON 响应") from None

        if not isinstance(payload, dict):
            raise DingTalkError("钉钉返回了无法识别的响应")
        code = payload.get("errcode", payload.get("code"))
        if code not in (None, 0, "0", "OK"):
            raise DingTalkError(_api_message(payload))
        return payload


class DingTalkClient:
    def __init__(self, client_id: str, client_secret: str, http: HttpClient) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http
        self._token: str | None = None

    def token(self) -> str:
        if self._token is None:
            payload = self._http.request_json(
                "GET",
                "https://oapi.dingtalk.com/gettoken",
                query={
                    "appkey": self._client_id,
                    "appsecret": self._client_secret,
                },
            )
            token = payload.get("access_token")
            if not isinstance(token, str) or not token:
                raise DingTalkError("钉钉鉴权成功但未返回 access_token")
            self._token = token
        return self._token

    def operator_union_id(self, user_id: str) -> str:
        payload = self._http.request_json(
            "POST",
            "https://oapi.dingtalk.com/topapi/v2/user/get",
            query={"access_token": self.token()},
            json_body={"userid": user_id},
        )
        result = payload.get("result", {})
        union_id = result.get("unionid") if isinstance(result, dict) else None
        if not isinstance(union_id, str) or not union_id:
            raise DingTalkError("无法取得项目表操作人的 unionid")
        return union_id

    def direct_subdepartments(self, department_id: int) -> list[dict[str, Any]]:
        payload = self._http.request_json(
            "POST",
            "https://oapi.dingtalk.com/topapi/v2/department/listsub",
            query={"access_token": self.token()},
            json_body={"dept_id": department_id},
        )
        result = payload.get("result", [])
        if not isinstance(result, list):
            raise DingTalkError("通讯录部门响应中的 result 不是列表")
        return [item for item in result if isinstance(item, dict)]

    def find_department(self, department_name: str) -> dict[str, Any]:
        queue = [1]
        visited: set[int] = set()
        matches: list[dict[str, Any]] = []
        while queue:
            parent_id = queue.pop(0)
            if parent_id in visited:
                continue
            visited.add(parent_id)
            for department in self.direct_subdepartments(parent_id):
                raw_id = department.get("dept_id") or department.get("deptId")
                if raw_id is None:
                    continue
                department_id = int(raw_id)
                queue.append(department_id)
                if str(department.get("name", "")).strip() == department_name:
                    matches.append(department)
            if len(visited) > 2_000:
                raise DingTalkError("通讯录部门层级异常，已停止遍历")
        if not matches:
            raise DingTalkError(f"通讯录中找不到部门“{department_name}”")
        if len(matches) > 1:
            raise DingTalkError(f"通讯录中有多个同名部门“{department_name}”")
        return matches[0]

    def department_users(
        self, department_id: int
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        users: list[dict[str, Any]] = []
        cursor = 0
        pages = 0
        while True:
            payload = self._http.request_json(
                "POST",
                "https://oapi.dingtalk.com/topapi/user/listsimple",
                query={"access_token": self.token()},
                json_body={
                    "dept_id": department_id,
                    "cursor": cursor,
                    "size": 100,
                },
            )
            result = payload.get("result", {})
            if not isinstance(result, dict):
                raise DingTalkError("通讯录人员响应中的 result 不是对象")
            page_users = result.get("list", [])
            if not isinstance(page_users, list):
                raise DingTalkError("通讯录人员响应中的 list 不是列表")
            users.extend(item for item in page_users if isinstance(item, dict))
            pages += 1
            if not bool(result.get("has_more")):
                return users, {
                    "pages": pages,
                    "records": len(users),
                    "has_more": False,
                    "complete": True,
                }
            next_cursor = result.get("next_cursor")
            if next_cursor is None or str(next_cursor) == str(cursor) or pages >= 100:
                raise DingTalkError("通讯录人员分页未能完整结束")
            cursor = int(next_cursor)

    def table_records(
        self, base_id: str, sheet_id: str, operator_id: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        endpoint = (
            f"https://api.dingtalk.com/v1.0/notable/bases/{base_id}"
            f"/sheets/{sheet_id}/records/list"
        )
        records: list[dict[str, Any]] = []
        page_token: str | None = None
        pages = 0
        while True:
            body: dict[str, Any] = {"maxResults": 100, "calcFields": True}
            if page_token:
                body["pageToken"] = page_token
            payload = self._http.request_json(
                "POST",
                endpoint,
                query={"operatorId": operator_id},
                json_body=body,
                headers={"x-acs-dingtalk-access-token": self.token()},
            )
            page_records = payload.get("records", [])
            if not isinstance(page_records, list):
                raise DingTalkError("项目表响应中的 records 不是列表")
            records.extend(item for item in page_records if isinstance(item, dict))
            pages += 1
            next_token = payload.get("nextToken") or payload.get("next_token")
            has_more = bool(payload.get("hasMore") or payload.get("has_more"))
            if not next_token:
                has_more = False
            if not has_more:
                return records, {
                    "pages": pages,
                    "records": len(records),
                    "has_more": False,
                    "complete": True,
                }
            if pages >= 100 or next_token == page_token:
                raise DingTalkError("项目表分页未能完整结束")
            page_token = str(next_token)

    def work_logs(
        self, user_id: str, start_ms: int, end_ms: int
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        logs: list[dict[str, Any]] = []
        cursor = 0
        pages = 0
        while True:
            payload = self._http.request_json(
                "POST",
                "https://oapi.dingtalk.com/topapi/report/list",
                query={"access_token": self.token()},
                form_body={
                    "start_time": start_ms,
                    "end_time": end_ms,
                    "cursor": cursor,
                    "size": 20,
                    "userid": user_id,
                },
            )
            result = payload.get("result", {})
            if not isinstance(result, dict):
                raise DingTalkError("工作日志响应中的 result 不是对象")
            page_logs = result.get("data_list", [])
            if not isinstance(page_logs, list):
                raise DingTalkError("工作日志响应中的 data_list 不是列表")
            logs.extend(item for item in page_logs if isinstance(item, dict))
            pages += 1
            has_more = bool(result.get("has_more"))
            if not has_more:
                return logs, {
                    "pages": pages,
                    "records": len(logs),
                    "has_more": False,
                    "complete": True,
                }
            next_cursor = result.get("next_cursor")
            if next_cursor is None or str(next_cursor) == str(cursor) or pages >= 100:
                raise DingTalkError(f"用户 {user_id} 的工作日志分页未能完整结束")
            cursor = int(next_cursor)


def normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        normalized = [normalize_value(item) for item in value]
        compact = [item for item in normalized if item not in (None, "", [], {})]
        if all(isinstance(item, (str, int, float, bool)) for item in compact):
            return "；".join(str(item) for item in compact)
        return compact
    if isinstance(value, dict):
        for key in ("value", "text", "name", "title"):
            if key in value and len(value) <= 4:
                return normalize_value(value[key])
        return {key: normalize_value(item) for key, item in value.items()}
    return str(value)


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields", {})
    normalized_fields: dict[str, Any] = {}
    if isinstance(fields, dict):
        for key, value in fields.items():
            normalized = normalize_value(value)
            if (
                isinstance(normalized, (int, float))
                and normalized > 100_000_000_000
                and any(marker in str(key) for marker in ("日期", "时间", "DDL", "ddl"))
            ):
                normalized = datetime.fromtimestamp(
                    normalized / 1000, SHANGHAI
                ).date().isoformat()
            normalized_fields[str(key)] = normalized
    return {
        "record_id": record.get("id") or record.get("recordId"),
        "created_at": record.get("createdAt") or record.get("created_at"),
        "modified_at": record.get("lastModifiedAt")
        or record.get("modifiedAt")
        or record.get("modified_at"),
        "fields": normalized_fields,
    }


def normalize_log(log: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    content: dict[str, Any] = {}
    contents = log.get("contents", [])
    if isinstance(contents, list):
        for item in contents:
            if isinstance(item, dict):
                key = item.get("key")
                if key:
                    content[str(key)] = normalize_value(item.get("value"))
    elif isinstance(contents, dict):
        content = {str(key): normalize_value(value) for key, value in contents.items()}
    create_time = log.get("create_time") or log.get("createTime")
    modified_time = log.get("modified_time") or log.get("modifiedTime")
    return {
        "report_id": log.get("report_id") or log.get("reportId"),
        "creator": log.get("creator_name") or log.get("creatorName") or fallback_name,
        "create_time": normalize_api_timestamp(create_time),
        "modified_time": normalize_api_timestamp(modified_time),
        "content": content,
        "remark": normalize_value(log.get("remark")),
    }


def normalize_api_timestamp(value: Any) -> Any:
    if isinstance(value, (int, float)) and value > 100_000_000_000:
        return datetime.fromtimestamp(value / 1000, SHANGHAI).isoformat()
    return value


def parse_as_of(raw: str | None) -> date:
    return date.fromisoformat(raw) if raw else datetime.now(SHANGHAI).date()


def epoch_milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def field_value(fields: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = fields.get(name)
        if value not in (None, ""):
            return value
    return None


def project_name(record: dict[str, Any]) -> str | None:
    fields = record.get("fields", {})
    if not isinstance(fields, dict):
        return None
    value = field_value(fields, ("项目名称", "产品名称", "项目", "产品"))
    return str(value).strip() if value else None


def project_status(record: dict[str, Any]) -> str | None:
    fields = record.get("fields", {})
    if not isinstance(fields, dict):
        return None
    value = field_value(fields, ("状态", "项目状态", "进度状态"))
    return str(value).strip() if value else None


def project_due_date(record: dict[str, Any]) -> date | None:
    fields = record.get("fields", {})
    if not isinstance(fields, dict):
        return None
    value = field_value(
        fields, ("到仓时间", "到仓日期", "预计到仓", "计划到仓", "到仓日")
    )
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def strip_product_variant(name: str) -> str:
    for marker in ("【", "（", "("):
        if marker in name:
            return name.split(marker, 1)[0].strip()
    return name.strip()


def select_project_records(
    records: list[dict[str, Any]],
    *,
    cutoff: date,
    active_statuses: set[str],
    requested_projects: list[str],
) -> list[dict[str, Any]]:
    requested = {strip_product_variant(item) for item in requested_projects}
    selected: list[dict[str, Any]] = []
    for record in records:
        name = project_name(record)
        if not name or project_status(record) not in active_statuses:
            continue
        if requested and strip_product_variant(name) not in requested:
            continue
        due = project_due_date(record)
        if due is not None and due > cutoff:
            continue
        selected.append(record)
    return sorted(
        selected,
        key=lambda item: (
            project_due_date(item) is None,
            project_due_date(item) or date.max,
            project_name(item) or "",
        ),
    )


def project_definitions(
    records: list[dict[str, Any]], profiles: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    profiles_by_name = {
        str(item.get("name", "")): item for item in profiles if item.get("name")
    }
    definitions: list[dict[str, Any]] = []
    for record in records:
        name = project_name(record)
        if not name:
            continue
        base_name = strip_product_variant(name)
        profile = profiles_by_name.get(base_name, {})
        aliases = list(dict.fromkeys([name, base_name, *profile.get("aliases", [])]))
        definitions.append(
            {
                "name": name,
                "aliases": aliases,
                "related_terms": profile.get("related_terms", []),
            }
        )
    return definitions


def relevant_to_projects(value: Any, projects: list[dict[str, Any]]) -> list[str]:
    text = json.dumps(value, ensure_ascii=False)
    matched: list[str] = []
    for project in projects:
        name = str(project.get("name", ""))
        aliases = project.get("aliases", [name])
        if any(str(alias) in text for alias in aliases if alias):
            matched.append(name)
    return matched


def related_project_hints(
    value: Any, projects: list[dict[str, Any]]
) -> list[str]:
    text = json.dumps(value, ensure_ascii=False)
    hinted: list[str] = []
    for project in projects:
        terms = project.get("related_terms", [])
        if any(str(term) in text for term in terms if term):
            hinted.append(str(project.get("name", "")))
    return hinted


def directory_scope(
    client: DingTalkClient,
    config: dict[str, Any],
    explicit_user_ids: list[str],
) -> tuple[dict[str, str], dict[str, Any]]:
    known_users = {
        str(item["user_id"]): str(item.get("name", item["user_id"]))
        for item in config.get("known_users", [])
        if isinstance(item, dict) and item.get("user_id")
    }
    if explicit_user_ids:
        return (
            {
                user_id: known_users.get(user_id, user_id)
                for user_id in explicit_user_ids
            },
            {
                "source": "explicit_user_ids",
                "records": len(explicit_user_ids),
                "complete": True,
            },
        )

    department_name = str(config["department_name"])
    department = client.find_department(department_name)
    department_id = int(department.get("dept_id") or department.get("deptId"))
    include_subdepartments = bool(config.get("include_subdepartments", False))
    department_ids = [department_id]
    if include_subdepartments:
        queue = [department_id]
        while queue:
            current_id = queue.pop(0)
            for child in client.direct_subdepartments(current_id):
                child_id = int(child.get("dept_id") or child.get("deptId"))
                department_ids.append(child_id)
                queue.append(child_id)

    all_users: list[dict[str, Any]] = []
    total_pages = 0
    for scoped_department_id in department_ids:
        users, completeness = client.department_users(scoped_department_id)
        all_users.extend(users)
        total_pages += int(completeness["pages"])

    excluded_names = {
        str(name).strip() for name in config.get("excluded_user_names", [])
    }
    users_by_id: dict[str, str] = {}
    for user in all_users:
        user_id = user.get("userid") or user.get("user_id") or user.get("userId")
        name = str(user.get("name", "")).strip()
        if user_id and name not in excluded_names:
            users_by_id[str(user_id)] = name or str(user_id)
    return users_by_id, {
        "source": "live_directory",
        "department_id": department_id,
        "department_name": department_name,
        "include_subdepartments": include_subdepartments,
        "excluded_names": sorted(excluded_names),
        "pages": total_pages,
        "records": len(users_by_id),
        "has_more": False,
        "complete": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="只读获取钉钉近期交付项目表和员工工作日志。"
    )
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--as-of")
    parser.add_argument("--log-days", type=int, default=14)
    parser.add_argument("--cutoff-days", type=int, default=30)
    parser.add_argument("--project", action="append", default=[])
    parser.add_argument("--user-id", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.log_days < 1 or args.cutoff_days < 0:
        raise ValueError("--log-days 必须大于 0，--cutoff-days 不能小于 0")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    client_id, client_secret = load_credentials(
        resolve_credentials_path(args.credentials_file)
    )
    client = DingTalkClient(client_id, client_secret, HttpClient(args.timeout))

    as_of = parse_as_of(args.as_of)
    log_start_date = as_of - timedelta(days=args.log_days - 1)
    log_start = datetime.combine(log_start_date, time.min, SHANGHAI)
    log_end = datetime.combine(as_of, time.max, SHANGHAI)
    cutoff = as_of + timedelta(days=args.cutoff_days)
    operator_id = str(config["operator_user_id"])
    union_id = client.operator_union_id(operator_id)
    raw_records, table_completeness = client.table_records(
        str(config["base_id"]), str(config["sheet_id"]), union_id
    )
    all_records = [normalize_record(item) for item in raw_records]
    records = select_project_records(
        all_records,
        cutoff=cutoff,
        active_statuses=set(config.get("active_statuses", ["进行中"])),
        requested_projects=args.project,
    )
    profiles = [
        item
        for item in config.get("project_profiles", [])
        if isinstance(item, dict)
    ]
    projects = project_definitions(records, profiles)
    for record in records:
        record["matched_projects"] = [project_name(record)]

    users_by_id, directory_completeness = directory_scope(
        client, config, args.user_id
    )
    user_ids = list(users_by_id)

    logs_by_user: dict[str, Any] = {}
    completeness_by_user: dict[str, Any] = {}
    for user_id in user_ids:
        try:
            raw_logs, completeness = client.work_logs(
                user_id, epoch_milliseconds(log_start), epoch_milliseconds(log_end)
            )
        except DingTalkError as exc:
            error = str(exc)
            logs_by_user[user_id] = {
                "name": users_by_id.get(user_id, user_id),
                "logs": [],
                "error": error,
            }
            completeness_by_user[user_id] = {
                "pages": 0,
                "records": 0,
                "has_more": None,
                "complete": False,
                "error": error,
            }
            continue
        normalized_logs = [
            normalize_log(item, users_by_id.get(user_id, user_id)) for item in raw_logs
        ]
        for log in normalized_logs:
            log["matched_projects"] = relevant_to_projects(log, projects)
            log["related_project_hints"] = related_project_hints(log, projects)
        logs_by_user[user_id] = {
            "name": users_by_id.get(user_id, user_id),
            "logs": normalized_logs,
        }
        completeness_by_user[user_id] = completeness

    return {
        "generated_at": datetime.now(SHANGHAI).isoformat(),
        "scope": {
            "as_of": as_of.isoformat(),
            "cutoff_date": cutoff.isoformat(),
            "log_start": log_start_date.isoformat(),
            "log_end": as_of.isoformat(),
            "department": config.get("department_name"),
            "projects": projects,
            "user_ids": user_ids,
        },
        "completeness": {
            "project_table": {
                **table_completeness,
                "selected_records": len(records),
            },
            "directory": directory_completeness,
            "logs_by_user": completeness_by_user,
        },
        "project_records": records,
        "logs_by_user": logs_by_user,
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = run(args)
        serialized = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(f"{serialized}\n", encoding="utf-8")
            args.output.chmod(0o600)
        else:
            print(serialized)
        return 0
    except (DingTalkError, ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
