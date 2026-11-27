#!/usr/bin/env python3
"""Create, inspect, wait for, and download Volcengine Seedance videos."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seedance-2-0-mini-260615"
MIN_DURATION_SECONDS = 4
MAX_DURATION_SECONDS = 15
SUPPORTED_MODELS: dict[str, dict[str, str]] = {
    "doubao-seedance-2-0-mini-260615": {
        "name": "Seedance 2.0 Mini",
        "capabilities": "成本更低，最高 720p",
    },
}
TERMINAL_STATUSES = {"succeeded", "failed", "expired", "cancelled"}
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_POLL_INTERVAL_SECONDS = 10.0
DEFAULT_MAX_WAIT_SECONDS = 3600.0
APPROVAL_TTL_SECONDS = 1800


class SeedanceError(RuntimeError):
    """A user-actionable Seedance client error."""


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    base_url: str


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SeedanceError(f"{path}:{line_number} 不是 KEY=VALUE 格式")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def bundle_env_path() -> Path:
    configured = os.environ.get("SKINCARE_VIDEO_ENV", "").strip()
    return Path(configured).expanduser() if configured else codex_home() / "skincare-video-bundle.env"


def resolve_model(model_override: str | None) -> str:
    dotenv = load_dotenv(bundle_env_path())
    model = model_override or os.environ.get("SEEDANCE_MODEL") or dotenv.get("SEEDANCE_MODEL") or DEFAULT_MODEL
    return validate_model(model)


def load_settings(model_override: str | None) -> Settings:
    env_path = bundle_env_path()
    dotenv = load_dotenv(env_path)
    api_key = os.environ.get("ARK_API_KEY") or dotenv.get("ARK_API_KEY", "")
    if not api_key:
        raise SeedanceError(f"请先在 {env_path} 中填写 ARK_API_KEY")
    model = resolve_model(model_override)
    base_url = os.environ.get("ARK_BASE_URL") or dotenv.get("ARK_BASE_URL", DEFAULT_BASE_URL)
    return Settings(api_key=api_key, model=model, base_url=base_url.rstrip("/"))


def validate_model(model: str) -> str:
    if model not in SUPPORTED_MODELS:
        raise SeedanceError(
            f"此 Skill 仅允许模型 {DEFAULT_MODEL}，拒绝使用 {model}"
        )
    return model


def model_catalog() -> dict[str, Any]:
    return {
        "default_model": DEFAULT_MODEL,
        "models": [
            {
                "name": details["name"],
                "model_id": model_id,
                "capabilities": details["capabilities"],
                "default": model_id == DEFAULT_MODEL,
            }
            for model_id, details in SUPPORTED_MODELS.items()
        ],
    }


class ArkClient:
    """HTTP boundary for the Ark content-generation task API."""

    def __init__(self, settings: Settings, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        self.settings = settings
        self.timeout_seconds = timeout_seconds

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Do not retry POST: a timed-out request may already have created a billable task.
        return self._request("POST", "/contents/generations/tasks", payload, retries=0)

    def get_task(self, task_id: str) -> dict[str, Any]:
        safe_task_id = validate_task_id(task_id)
        return self._request("GET", f"/contents/generations/tasks/{safe_task_id}", retries=3)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        retries: int = 0,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
        request = urllib.request.Request(
            f"{self.settings.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    return parse_json_response(response.read())
            except urllib.error.HTTPError as exc:
                error_body = parse_error_body(exc.read())
                if exc.code in RETRYABLE_STATUS_CODES and attempt < retries:
                    time.sleep(2**attempt)
                    continue
                raise SeedanceError(f"API 请求失败（HTTP {exc.code}）：{error_body}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < retries:
                    time.sleep(2**attempt)
                    continue
                raise SeedanceError(f"网络请求失败：{exc.reason if hasattr(exc, 'reason') else exc}") from exc
        raise SeedanceError("API 请求在重试后仍失败")


def parse_json_response(body: bytes) -> dict[str, Any]:
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SeedanceError("API 返回了无法解析的响应") from exc
    if not isinstance(result, dict):
        raise SeedanceError("API 返回结构不是 JSON 对象")
    return result


def parse_error_body(body: bytes) -> str:
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "响应正文不可解析"
    if not isinstance(parsed, dict):
        return "未知 API 错误"
    error = parsed.get("error")
    if isinstance(error, dict):
        code = error.get("code", "unknown")
        message = error.get("message", "未提供错误信息")
        return f"{code}: {message}"
    message = parsed.get("message")
    return str(message) if message else "未知 API 错误"


def validate_task_id(task_id: str) -> str:
    if not task_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in task_id):
        raise SeedanceError("任务 ID 含非法字符")
    return task_id


def media_url(source: str, media_kind: str) -> str:
    if source.startswith(("http://", "https://", "asset://", "data:")):
        return source
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise SeedanceError(f"素材文件不存在：{path}")
    if media_kind == "video":
        raise SeedanceError("参考视频不支持本地 Base64，请使用公网 URL 或 asset:// 素材 ID")
    limit = 30 * 1024 * 1024 if media_kind == "image" else 15 * 1024 * 1024
    if path.stat().st_size >= limit:
        raise SeedanceError(f"本地{media_kind}素材过大，请改用公网 URL 或 asset:// 素材 ID")
    mime_type = mimetypes.guess_type(path.name)[0]
    expected_prefix = f"{media_kind}/"
    if not mime_type or not mime_type.startswith(expected_prefix):
        raise SeedanceError(f"无法识别{media_kind}文件格式：{path.suffix}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_content(args: argparse.Namespace) -> list[dict[str, Any]]:
    has_frames = bool(args.first_frame or args.last_frame)
    has_references = bool(args.reference_image or args.reference_video or args.reference_audio)
    if not isinstance(args.prompt, str) or not args.prompt.strip():
        raise SeedanceError("prepare 必须提供已整理完成的模型 text（--model-text）")
    if args.last_frame and not args.first_frame:
        raise SeedanceError("使用 --last-frame 时必须同时提供 --first-frame")
    if has_frames and has_references:
        raise SeedanceError("首尾帧与多模态参考是互斥场景，不可混用")

    content: list[dict[str, Any]] = [{"type": "text", "text": args.prompt}]
    if args.first_frame:
        content.append({"type": "image_url", "image_url": {"url": media_url(args.first_frame, "image")}, "role": "first_frame"})
    if args.last_frame:
        content.append({"type": "image_url", "image_url": {"url": media_url(args.last_frame, "image")}, "role": "last_frame"})
    for source in args.reference_image:
        content.append({"type": "image_url", "image_url": {"url": media_url(source, "image")}, "role": "reference_image"})
    for source in args.reference_video:
        content.append({"type": "video_url", "video_url": {"url": media_url(source, "video")}, "role": "reference_video"})
    for source in args.reference_audio:
        content.append({"type": "audio_url", "audio_url": {"url": media_url(source, "audio")}, "role": "reference_audio"})
    return content


def build_payload(args: argparse.Namespace, model: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "content": build_content(args)}
    option_names = (
        "resolution", "ratio", "duration", "seed", "watermark",
        "generate_audio", "return_last_frame", "output_format", "callback_url",
        "execution_expires_after", "priority", "service_tier", "safety_identifier",
    )
    for name in option_names:
        value = getattr(args, name, None)
        if value is not None:
            payload[name] = value
    validate_payload_model_compatibility(payload)
    return payload


def generation_summary(args: argparse.Namespace, model: str) -> dict[str, Any]:
    option_names = (
        "resolution", "ratio", "duration", "seed", "watermark",
        "generate_audio", "return_last_frame", "output_format", "callback_url",
        "execution_expires_after", "priority", "service_tier", "safety_identifier",
    )
    return {
        "model": model,
        "model_text": args.prompt,
        "first_frame": args.first_frame,
        "last_frame": args.last_frame,
        "reference_images": list(args.reference_image),
        "reference_videos": list(args.reference_video),
        "reference_audios": list(args.reference_audio),
        "parameters": {
            name: value
            for name in option_names
            if (value := getattr(args, name, None)) is not None
        },
    }


def validate_payload_model_compatibility(payload: dict[str, Any]) -> None:
    if "camera_fixed" in payload:
        raise SeedanceError(
            "批准单包含 Seedance 2.0 Mini 不支持的 camera_fixed；"
            "请将固定机位要求写入 model_text 后重新 prepare 并确认"
        )
    duration = payload.get("duration")
    if duration is not None and (
        isinstance(duration, bool)
        or not isinstance(duration, int)
        or not MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS
    ):
        raise SeedanceError(
            "Seedance 2.0 Mini 的 duration 必须是 "
            f"{MIN_DURATION_SECONDS}–{MAX_DURATION_SECONDS} 秒整数"
        )


class ApprovalStore:
    """Persist one-time human approvals for billable task submissions."""

    def __init__(self, directory: Path | None = None, ttl_seconds: int = APPROVAL_TTL_SECONDS):
        self.directory = directory or (skill_root() / ".approvals")
        self.ttl_seconds = ttl_seconds

    def prepare(self, payload: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        approval_id = secrets.token_hex(12)
        now = int(time.time())
        record = {
            "approval_id": approval_id,
            "status": "prepared",
            "created_at": now,
            "expires_at": now + self.ttl_seconds,
            "request": summary,
            "payload": payload,
        }
        self._write_new(self._path(approval_id, "prepared"), record)
        return {
            "approval_id": approval_id,
            "status": "awaiting_human_confirmation",
            "expires_at": record["expires_at"],
            "request": summary,
            "confirmation_prompt": "请确认以上 model_text 和全部参数；确认后才会提交计费任务。",
            "next_step": f"人类明确确认后运行：seedance.py approve {approval_id}",
        }

    def approve(self, approval_id: str) -> dict[str, Any]:
        prepared_path = self._path(approval_id, "prepared")
        record = self._read(prepared_path, "待确认参数不存在或已处理")
        self._validate_not_expired(record)
        record["status"] = "approved"
        record["approved_at"] = int(time.time())
        approved_path = self._path(approval_id, "approved")
        self._write_new(approved_path, record)
        prepared_path.unlink()
        return {
            "approval_id": approval_id,
            "status": "approved",
            "expires_at": record["expires_at"],
            "request": record["request"],
            "next_step": f"运行：seedance.py submit {approval_id}",
        }

    def consume(self, approval_id: str) -> dict[str, Any]:
        approved_path = self._path(approval_id, "approved")
        record = self._read(approved_path, "批准单不存在、未确认或已使用")
        self._validate_not_expired(record)
        used_path = self._path(approval_id, "used")
        try:
            os.link(approved_path, used_path)
            approved_path.unlink()
        except FileExistsError as exc:
            raise SeedanceError("批准单已经使用，禁止重复提交") from exc
        except FileNotFoundError as exc:
            raise SeedanceError("批准单已被其他进程使用，禁止重复提交") from exc
        return record

    def _path(self, approval_id: str, state: str) -> Path:
        safe_id = validate_approval_id(approval_id)
        return self.directory / f"{safe_id}.{state}.json"

    @staticmethod
    def _validate_not_expired(record: dict[str, Any]) -> None:
        expires_at = record.get("expires_at")
        if not isinstance(expires_at, int) or int(time.time()) > expires_at:
            raise SeedanceError("批准单已过期，请重新 prepare 并让人类确认")

    @staticmethod
    def _read(path: Path, missing_message: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SeedanceError(missing_message) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise SeedanceError("批准单损坏，禁止提交") from exc
        if not isinstance(value, dict) or not isinstance(value.get("payload"), dict):
            raise SeedanceError("批准单结构无效，禁止提交")
        return value

    @staticmethod
    def _write_new(path: Path, value: dict[str, Any]) -> None:
        try:
            with path.open("x", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
            path.chmod(0o600)
        except FileExistsError as exc:
            raise SeedanceError("批准单状态冲突，禁止继续") from exc


def validate_approval_id(approval_id: str) -> str:
    if len(approval_id) != 24 or any(character not in "0123456789abcdef" for character in approval_id):
        raise SeedanceError("批准单 ID 格式无效")
    return approval_id


def wait_for_task(client: ArkClient, task_id: str, poll_interval: float, max_wait: float) -> dict[str, Any]:
    deadline = time.monotonic() + max_wait
    last_status: str | None = None
    while True:
        task = client.get_task(task_id)
        status = str(task.get("status", "unknown"))
        if status != last_status:
            print(json.dumps({"task_id": task_id, "status": status}, ensure_ascii=False), file=sys.stderr)
            last_status = status
        if status in TERMINAL_STATUSES:
            return task
        if time.monotonic() >= deadline:
            raise SeedanceError(f"等待超过 {max_wait:g} 秒；任务 {task_id} 当前状态为 {status}")
        time.sleep(poll_interval)


def extract_output_url(task: dict[str, Any], key: str) -> str | None:
    content = task.get("content")
    if isinstance(content, dict):
        value = content.get(key)
        return value if isinstance(value, str) and value else None
    return None


def download_file(url: str, output: Path, overwrite: bool) -> Path:
    target = output.expanduser().resolve()
    if target.exists() and not overwrite:
        raise SeedanceError(f"输出文件已存在：{target}；使用 --overwrite 允许覆盖")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.part")
    try:
        with urllib.request.urlopen(url, timeout=DEFAULT_TIMEOUT_SECONDS) as response, temporary.open("wb") as file_handle:
            while chunk := response.read(1024 * 1024):
                file_handle.write(chunk)
        temporary.replace(target)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        temporary.unlink(missing_ok=True)
        raise SeedanceError(f"下载结果失败：{exc}") from exc
    return target


def default_output(task_id: str, task: dict[str, Any]) -> Path:
    content = task.get("content")
    extension = "mp4"
    if isinstance(content, dict) and content.get("video_url", "").lower().split("?", 1)[0].endswith(".mov"):
        extension = "mov"
    return Path.cwd() / f"seedance-{task_id}.{extension}"


def add_wait_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument("--max-wait", type=float, default=DEFAULT_MAX_WAIT_SECONDS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--last-frame-output", type=Path)
    parser.add_argument("--overwrite", action="store_true")


def add_generation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model-text",
        "--prompt",
        dest="prompt",
        required=True,
        help="已整理完成、将原样发送给模型并向用户确认的 text",
    )
    parser.add_argument("--model")
    parser.add_argument("--first-frame")
    parser.add_argument("--last-frame")
    parser.add_argument("--reference-image", action="append", default=[])
    parser.add_argument("--reference-video", action="append", default=[])
    parser.add_argument("--reference-audio", action="append", default=[])
    parser.add_argument("--resolution", choices=("480p", "720p", "1080p", "4k"))
    parser.add_argument("--ratio", choices=("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"))
    parser.add_argument(
        "--duration",
        type=int,
        choices=range(MIN_DURATION_SECONDS, MAX_DURATION_SECONDS + 1),
        metavar="SECONDS",
        help=f"生成时长，必须为 {MIN_DURATION_SECONDS}–{MAX_DURATION_SECONDS} 秒整数",
    )
    parser.add_argument("--seed", type=int)
    parser.add_argument("--watermark", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--generate-audio", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--return-last-frame", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--output-format", choices=("mp4", "mov"))
    parser.add_argument("--callback-url")
    parser.add_argument("--execution-expires-after", type=int)
    parser.add_argument("--priority", type=int, choices=range(10))
    parser.add_argument("--service-tier", choices=("default", "flex"))
    parser.add_argument("--safety-identifier")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="调用火山方舟 Seedance 视频生成 API")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("models", help="列出 Skill 支持的模型和默认模型")

    prepare = subparsers.add_parser("prepare", help="准备并展示待人工确认的生成参数，不调用 API")
    add_generation_options(prepare)

    approve = subparsers.add_parser("approve", help="在人类明确确认后批准一次提交")
    approve.add_argument("approval_id")

    submit = subparsers.add_parser("submit", help="提交已批准的生成任务，并默认等待和下载")
    submit.add_argument("approval_id")
    submit.add_argument("--no-wait", action="store_true")
    add_wait_options(submit)

    status = subparsers.add_parser("status", help="查询任务状态")
    status.add_argument("task_id")
    status.add_argument("--model")

    wait = subparsers.add_parser("wait", help="等待已有任务并下载")
    wait.add_argument("task_id")
    wait.add_argument("--model")
    add_wait_options(wait)
    return parser


def validate_wait_options(args: argparse.Namespace) -> None:
    if args.poll_interval <= 0:
        raise SeedanceError("--poll-interval 必须大于 0")
    if args.max_wait <= 0:
        raise SeedanceError("--max-wait 必须大于 0")


def finish_task(task: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    status = task.get("status")
    if status != "succeeded":
        error = task.get("error")
        raise SeedanceError(f"任务结束但未成功（status={status}）：{error or '未提供错误详情'}")
    task_id = str(task.get("id", "unknown"))
    video_url = extract_output_url(task, "video_url")
    if not video_url:
        raise SeedanceError("任务成功，但响应中没有 content.video_url")
    video_path = download_file(video_url, args.output or default_output(task_id, task), args.overwrite)
    result: dict[str, Any] = {"id": task_id, "status": status, "video_path": str(video_path)}
    last_frame_url = extract_output_url(task, "last_frame_url")
    if args.last_frame_output and last_frame_url:
        result["last_frame_path"] = str(download_file(last_frame_url, args.last_frame_output, args.overwrite))
    elif args.last_frame_output:
        result["last_frame_warning"] = "响应中没有 content.last_frame_url"
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "models":
        return model_catalog()
    approvals = ApprovalStore()
    if args.command == "prepare":
        model = resolve_model(args.model)
        payload = build_payload(args, model)
        return approvals.prepare(payload, generation_summary(args, model))
    if args.command == "approve":
        return approvals.approve(args.approval_id)
    if args.command == "submit":
        validate_wait_options(args)
        record = approvals.consume(args.approval_id)
        payload = record["payload"]
        validate_payload_model_compatibility(payload)
        model = payload.get("model")
        if not isinstance(model, str):
            raise SeedanceError("批准单缺少有效模型，禁止提交")
        client = ArkClient(load_settings(model))
        created = client.create_task(payload)
        task_id = created.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise SeedanceError("创建任务成功，但响应中没有有效任务 ID")
        if args.no_wait:
            return {"id": task_id, "status": created.get("status", "submitted")}
        task = wait_for_task(client, task_id, args.poll_interval, args.max_wait)
        return finish_task(task, args)

    settings = load_settings(args.model)
    client = ArkClient(settings)
    if args.command == "status":
        return client.get_task(args.task_id)
    validate_wait_options(args)
    if args.command == "wait":
        return finish_task(wait_for_task(client, args.task_id, args.poll_interval, args.max_wait), args)
    raise SeedanceError(f"不支持命令：{args.command}")


def main() -> int:
    try:
        result = run(build_parser().parse_args())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except SeedanceError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
