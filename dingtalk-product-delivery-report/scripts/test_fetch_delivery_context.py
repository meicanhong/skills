#!/usr/bin/env python3
"""Unit tests for fetch_delivery_context.py."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("fetch_delivery_context.py")
SPEC = importlib.util.spec_from_file_location("fetch_delivery_context", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ParseEnvFileTests(unittest.TestCase):
    def test_parses_export_quotes_and_embedded_equals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.env"
            path.write_text(
                "# comment\n"
                "export DWS_CLIENT_ID='client-id'\n"
                'DWS_CLIENT_SECRET=\"secret=part\"\n',
                encoding="utf-8",
            )
            self.assertEqual(
                MODULE.parse_env_file(path),
                {
                    "DWS_CLIENT_ID": "client-id",
                    "DWS_CLIENT_SECRET": "secret=part",
                },
            )

    def test_environment_overrides_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.env"
            path.write_text(
                "DWS_CLIENT_ID=file-id\nDWS_CLIENT_SECRET=file-secret\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "DWS_CLIENT_ID": "env-id",
                    "DWS_CLIENT_SECRET": "env-secret",
                },
                clear=False,
            ):
                self.assertEqual(
                    MODULE.load_credentials(path), ("env-id", "env-secret")
                )

    def test_uses_bundled_env_when_no_explicit_path_is_given(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            default_path = Path(directory) / ".env"
            default_path.write_text(
                "DWS_CLIENT_ID=client-id\nDWS_CLIENT_SECRET=client-secret\n",
                encoding="utf-8",
            )
            with patch.object(MODULE, "DEFAULT_CREDENTIALS", default_path):
                self.assertEqual(MODULE.resolve_credentials_path(None), default_path)

    def test_explicit_credentials_path_has_priority(self) -> None:
        explicit_path = Path("/tmp/explicit-credentials.env")
        self.assertEqual(
            MODULE.resolve_credentials_path(explicit_path), explicit_path
        )


class NormalizationTests(unittest.TestCase):
    def test_normalizes_nested_table_values(self) -> None:
        record = MODULE.normalize_record(
            {
                "id": "record-1",
                "fields": {
                    "负责人": [{"name": "龙晓婷"}],
                    "状态": {"value": "进行中"},
                    "数量": 6000,
                    "到仓时间": 1785340800000,
                },
            }
        )
        self.assertEqual(record["fields"]["负责人"], "龙晓婷")
        self.assertEqual(record["fields"]["状态"], "进行中")
        self.assertEqual(record["fields"]["数量"], 6000)
        self.assertEqual(record["fields"]["到仓时间"], "2026-07-30")

    def test_normalizes_log_contents(self) -> None:
        log = MODULE.normalize_log(
            {
                "creator_name": "宋昊",
                "contents": [
                    {"key": "今日完成工作", "value": "人体报告已出"},
                    {"key": "需协调与帮助", "value": "无"},
                ],
            },
            "fallback",
        )
        self.assertEqual(log["creator"], "宋昊")
        self.assertEqual(log["content"]["今日完成工作"], "人体报告已出")


class ScopeTests(unittest.TestCase):
    def test_date_window_is_inclusive_for_fourteen_days(self) -> None:
        as_of = date.fromisoformat("2026-07-30")
        start = as_of - MODULE.timedelta(days=14 - 1)
        cutoff = as_of + MODULE.timedelta(days=30)
        self.assertEqual(start.isoformat(), "2026-07-17")
        self.assertEqual(cutoff.isoformat(), "2026-08-29")

    def test_epoch_uses_shanghai_timezone(self) -> None:
        value = datetime(2026, 7, 30, 0, 0, tzinfo=MODULE.SHANGHAI)
        self.assertEqual(MODULE.epoch_milliseconds(value), 1785340800000)

    def test_matches_project_aliases(self) -> None:
        projects = [
            {"name": "新版特证冻膜", "aliases": ["冻膜", "芭薇"]},
            {"name": "新防晒", "aliases": ["防晒"]},
        ]
        self.assertEqual(
            MODULE.relevant_to_projects({"text": "芭薇样品未到"}, projects),
            ["新版特证冻膜"],
        )

    def test_related_terms_are_hints_not_direct_matches(self) -> None:
        projects = [
            {
                "name": "新版特证冻膜",
                "aliases": ["新版特证冻膜"],
                "related_terms": ["芭薇"],
            }
        ]
        log = {"text": "芭薇样品未到"}
        self.assertEqual(MODULE.relevant_to_projects(log, projects), [])
        self.assertEqual(
            MODULE.related_project_hints(log, projects), ["新版特证冻膜"]
        )

    def test_table_matching_uses_project_name_not_supplier_notes(self) -> None:
        records = [
            {
                "fields": {
                    "项目名称": "胶原乳霜",
                    "状态": "进行中",
                    "到仓时间": "2026-12-01",
                    "备注说明": "蜜妆集中打样",
                }
            },
            {
                "fields": {
                    "项目名称": "新版特证美白霜",
                    "状态": "进行中",
                    "到仓时间": "2026-07-31",
                }
            },
            {
                "fields": {
                    "项目名称": "已完成项目",
                    "状态": "已完成",
                    "到仓时间": "2026-07-30",
                }
            },
        ]
        selected = MODULE.select_project_records(
            records,
            cutoff=date.fromisoformat("2026-08-29"),
            active_statuses={"进行中"},
            requested_projects=[],
        )
        self.assertEqual(
            [MODULE.project_name(item) for item in selected],
            ["新版特证美白霜"],
        )

    def test_project_override_filters_dynamic_scope(self) -> None:
        records = [
            {
                "fields": {
                    "项目名称": "新版特证冻膜【50g软管】",
                    "状态": "进行中",
                    "到仓时间": "2026-07-31",
                }
            },
            {
                "fields": {
                    "项目名称": "新防晒",
                    "状态": "进行中",
                    "到仓时间": "2026-07-30",
                }
            },
        ]
        selected = MODULE.select_project_records(
            records,
            cutoff=date.fromisoformat("2026-08-29"),
            active_statuses={"进行中"},
            requested_projects=["新版特证冻膜"],
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(MODULE.project_name(selected[0]), "新版特证冻膜【50g软管】")


if __name__ == "__main__":
    unittest.main()
