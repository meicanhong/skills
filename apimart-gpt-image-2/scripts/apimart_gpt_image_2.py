#!/usr/bin/env python3
"""APIMart gpt-image-2 command-line client using the Python stdlib."""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


BASE_URL = "https://api.apimart.ai"
MODEL = "gpt-image-2"
API_KEY_ENV = "APIMART_API_KEY"
SKILL_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = SKILL_DIR / ".env"
RATIOS = {
    "auto", "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5",
    "16:9", "9:16", "2:1", "1:2", "3:1", "1:3", "21:9", "9:21",
}
UPLOAD_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ACTIVE_STATUSES = {"submitted", "pending", "in_progress", "processing"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
RETRYABLE_STATUS_CODES = {429, 500, 502, 503}
LOGGER = logging.getLogger("apimart_gpt_image_2")


class ClientError(RuntimeError):
    """Represent a validated input, HTTP, API, or response-shape failure."""


def emit_log(event: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"event": event, **fields}, ensure_ascii=False))


def load_api_key_from_env_file(path: Path) -> str:
    """Read APIMART_API_KEY as inert text without executing dotenv content."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise ClientError(f"无法读取 API Key 文件 {path}: {exc}") from exc

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, value = stripped.partition("=")
        if separator and key.strip() == API_KEY_ENV:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            return value.strip()
    return ""


def require_api_key() -> str:
    api_key = load_api_key_from_env_file(ENV_FILE) or os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        raise ClientError(f"缺少 {API_KEY_ENV}；请填写 {ENV_FILE}，不要在聊天中粘贴密钥")
    return api_key


def parse_json_response(response: Any) -> dict[str, Any]:
    raw = response.read().decode("utf-8", errors="replace")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ClientError(f"API 返回了非 JSON 响应（HTTP {response.status}）") from exc
    if not isinstance(value, dict):
        raise ClientError("API JSON 顶层不是对象")
    return value


def describe_http_error(exc: urllib.error.HTTPError) -> ClientError:
    raw = exc.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    error_type = error.get("type", "http_error") if isinstance(error, dict) else "http_error"
    message = error.get("message", raw[:500]) if isinstance(error, dict) else raw[:500]
    return ClientError(f"APIMart HTTP {exc.code} [{error_type}]: {message}")


def request_json(
    method: str,
    path: str,
    api_key: str,
    *,
    body: bytes | None = None,
    content_type: str | None = None,
    retry_read: bool = False,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    attempts = 4 if retry_read and method == "GET" else 1
    for attempt in range(attempts):
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = parse_json_response(response)
                emit_log("api_request", method=method, path=path, status=response.status,
                         duration_ms=round((time.monotonic() - started) * 1000), retry_count=attempt)
                return payload
        except urllib.error.HTTPError as exc:
            if attempt + 1 < attempts and exc.code in RETRYABLE_STATUS_CODES:
                delay = 2 ** attempt
                emit_log("api_retry", method=method, path=path, status=exc.code,
                         retry_count=attempt + 1, delay_seconds=delay)
                time.sleep(delay)
                continue
            raise describe_http_error(exc) from exc
        except urllib.error.URLError as exc:
            if attempt + 1 < attempts:
                delay = 2 ** attempt
                emit_log("api_retry", method=method, path=path, error_type="network_error",
                         retry_count=attempt + 1, delay_seconds=delay)
                time.sleep(delay)
                continue
            raise ClientError(f"APIMart 网络请求失败: {exc.reason}") from exc
    raise ClientError("APIMart 请求未返回结果")


def validate_upload(path: Path) -> str:
    if not path.is_file():
        raise ClientError(f"图片文件不存在: {path}")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ClientError(f"图片超过 20MB: {path}")
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if mime_type not in UPLOAD_TYPES:
        raise ClientError(f"不支持的图片格式 {mime_type}: {path}")
    return mime_type


def upload_image(path: Path, api_key: str) -> str:
    mime_type = validate_upload(path)
    boundary = f"----apimart-{uuid.uuid4().hex}"
    safe_name = path.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8")
    body = prefix + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("ascii")
    payload = request_json(
        "POST", "/v1/uploads/images", api_key, body=body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    url = payload.get("url")
    if not isinstance(url, str) or not url:
        raise ClientError("上传响应缺少 url")
    return url


def validate_size(value: str) -> str:
    if value in RATIOS:
        return value
    match = re.fullmatch(r"([1-9]\d{1,4})x([1-9]\d{1,4})", value)
    if not match:
        raise argparse.ArgumentTypeError("size 必须是受支持的比例、auto 或 WIDTHxHEIGHT")
    return value


def validate_http_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("图片 URL 必须是有效的 HTTP(S) 公网 URL")
    return value


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正整数")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须是正数")
    return parsed


def build_generation_payload(args: argparse.Namespace, image_urls: list[str]) -> dict[str, Any]:
    prompt = args.prompt.strip()
    if not prompt:
        raise ClientError("prompt 不能为空")
    if len(image_urls) > 16:
        raise ClientError("参考图最多 16 张")
    payload: dict[str, Any] = {
        "model": MODEL,
        "prompt": prompt,
        "size": args.size,
        "resolution": args.resolution,
        "n": args.n,
        "official_fallback": False,
    }
    if image_urls:
        payload["image_urls"] = image_urls
    return payload


def extract_task_id(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise ClientError("生成响应缺少 data[0]")
    task_id = data[0].get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ClientError("生成响应缺少 task_id")
    return task_id


def get_task(task_id: str, api_key: str, language: str = "zh") -> dict[str, Any]:
    quoted_id = urllib.parse.quote(task_id, safe="")
    payload = request_json("GET", f"/v1/tasks/{quoted_id}?language={language}", api_key, retry_read=True)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ClientError("任务响应缺少 data 对象")
    return data


def wait_for_task(task_id: str, api_key: str, timeout: int, interval: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        task = get_task(task_id, api_key)
        status = task.get("status")
        emit_log("task_status", task_id=task_id, status=status, progress=task.get("progress"))
        if status in TERMINAL_STATUSES:
            return task
        if status not in ACTIVE_STATUSES:
            raise ClientError(f"未知任务状态: {status!r}")
        if time.monotonic() >= deadline:
            raise ClientError(f"等待任务超时（{timeout} 秒），task_id={task_id}")
        time.sleep(interval)


def collect_image_urls(task: dict[str, Any]) -> list[tuple[str, int | None]]:
    result = task.get("result")
    images = result.get("images") if isinstance(result, dict) else None
    if not isinstance(images, list):
        raise ClientError("已完成任务缺少 result.images")
    collected: list[tuple[str, int | None]] = []
    for image in images:
        if not isinstance(image, dict):
            continue
        urls = image.get("url")
        if isinstance(urls, str):
            urls = [urls]
        if isinstance(urls, list):
            for url in urls:
                if isinstance(url, str) and url:
                    collected.append((url, image.get("expires_at")))
    if not collected:
        raise ClientError("已完成任务没有可用图片 URL")
    return collected


def download_images(task_id: str, images: list[tuple[str, int | None]], output_dir: Path) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict[str, Any]] = []
    for index, (url, expires_at) in enumerate(images, start=1):
        try:
            validate_http_url(url)
        except argparse.ArgumentTypeError as exc:
            raise ClientError(f"任务返回了不安全的图片 URL: {url}") from exc
        suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            suffix = ".png"
        path = output_dir / f"{task_id}-{index}{suffix}"
        if path.exists():
            raise ClientError(f"拒绝覆盖已有文件: {path}")
        try:
            with urllib.request.urlopen(url, timeout=120) as response, path.open("wb") as handle:
                handle.write(response.read())
        except (urllib.error.URLError, OSError) as exc:
            raise ClientError(f"下载图片失败 {url}: {exc}") from exc
        downloaded.append({"path": str(path.resolve()), "url": url, "expires_at": expires_at})
    return downloaded


def command_generate(args: argparse.Namespace) -> dict[str, Any]:
    if args.dry_run and args.image:
        raise ClientError("dry-run 不上传本地文件；请改用 --image-url 验证请求")
    remote_images = list(args.image_url)
    if args.dry_run:
        return {"dry_run": True, "request": build_generation_payload(args, remote_images)}

    api_key = require_api_key()
    for image_path in args.image:
        remote_images.append(upload_image(Path(image_path), api_key))
    payload = build_generation_payload(args, remote_images)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    submitted = request_json("POST", "/v1/images/generations", api_key, body=body, content_type="application/json")
    task_id = extract_task_id(submitted)
    result: dict[str, Any] = {"task_id": task_id, "submitted": submitted}
    if not args.wait:
        return result
    task = wait_for_task(task_id, api_key, args.timeout, args.poll_interval)
    result["task"] = task
    if task.get("status") == "completed":
        result["images"] = download_images(task_id, collect_image_urls(task), Path(args.output_dir))
    return result


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    api_key = require_api_key()
    task = get_task(args.task_id, api_key, args.language)
    return {"task_id": args.task_id, "task": task}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="调用 APIMart gpt-image-2 API（禁用官方渠道兜底）")
    parser.add_argument("--verbose", action="store_true", help="向 stderr 输出结构化诊断日志")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="创建图像生成或编辑任务")
    generate.add_argument("--prompt", required=True)
    generate.add_argument("--size", default="1:1", type=validate_size)
    generate.add_argument("--resolution", choices=["1k", "2k", "4k"], default="1k")
    generate.add_argument("--n", type=int, choices=[1], default=1)
    generate.add_argument("--image", action="append", default=[], metavar="PATH")
    generate.add_argument("--image-url", action="append", default=[], type=validate_http_url, metavar="URL")
    generate.add_argument("--wait", action="store_true")
    generate.add_argument("--timeout", type=positive_int, default=900)
    generate.add_argument("--poll-interval", type=positive_float, default=3.0)
    generate.add_argument("--output-dir", default="./outputs")
    generate.add_argument("--dry-run", action="store_true")
    generate.set_defaults(handler=command_generate)

    status = subparsers.add_parser("status", help="查询任务状态")
    status.add_argument("task_id")
    status.add_argument("--language", choices=["zh", "en", "ko", "ja"], default="zh")
    status.set_defaults(handler=command_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")
    try:
        result = args.handler(args)
    except ClientError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
