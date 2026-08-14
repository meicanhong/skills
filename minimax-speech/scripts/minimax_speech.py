#!/usr/bin/env python3
"""MiniMax Speech 2.8 HD voice cloning and synthesis CLI."""

from __future__ import annotations

import argparse
import binascii
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("minimax_speech")
MODEL = "speech-2.8-hd"
DEFAULT_API_BASE = "https://api.minimaxi.com"
MAX_FILE_BYTES = 20 * 1024 * 1024
VOICE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{6,254}[A-Za-z0-9]$")


class MiniMaxError(RuntimeError):
    """Raised when validation, transport, or MiniMax API processing fails."""


def _codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _bundle_env_path() -> Path:
    configured = os.environ.get("SKINCARE_VIDEO_ENV", "").strip()
    return Path(configured).expanduser() if configured else _codex_home() / "skincare-video-bundle.env"


@dataclass(frozen=True)
class ClientConfig:
    api_key: str
    api_base: str
    timeout_seconds: float


class MiniMaxClient:
    """Own HTTP transport and MiniMax response validation."""

    def __init__(self, config: ClientConfig) -> None:
        self._config = config

    def upload_file(self, path: Path, purpose: str) -> int:
        boundary = f"----codex-{uuid.uuid4().hex}"
        body = _build_multipart_body(boundary, path, purpose)
        response = self._request(
            "/v1/files/upload",
            body,
            f"multipart/form-data; boundary={boundary}",
        )
        try:
            return int(response["file"]["file_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MiniMaxError("上传成功响应缺少 file.file_id") from exc

    def clone_voice(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/v1/voice_clone", payload)

    def list_voices(self, voice_type: str) -> dict[str, Any]:
        return self._post_json("/v1/get_voice", {"voice_type": voice_type})

    def synthesize(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/v1/t2a_v2", payload)

    def download(self, url: str) -> bytes:
        request = urllib.request.Request(url, method="GET")
        return self._open(request)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._request(path, body, "application/json")

    def _request(self, path: str, body: bytes, content_type: str) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self._config.api_base}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": content_type,
                "Accept": "application/json",
            },
            method="POST",
        )
        raw = self._open(request)
        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MiniMaxError("MiniMax 返回了无法解析的 JSON") from exc
        if not isinstance(response, dict):
            raise MiniMaxError("MiniMax 返回的 JSON 顶层不是对象")
        _raise_for_api_error(response)
        return response

    def _open(self, request: urllib.request.Request) -> bytes:
        try:
            with urllib.request.urlopen(
                request, timeout=self._config.timeout_seconds
            ) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = _safe_http_error_detail(exc)
            raise MiniMaxError(f"MiniMax HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise MiniMaxError(f"MiniMax 网络请求失败: {exc.reason}") from exc


def _build_multipart_body(boundary: str, path: Path, purpose: str) -> bytes:
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded_filename = urllib.parse.quote(path.name, safe="")
    fallback_filename = f"upload{path.suffix.lower()}"
    chunks = [
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="purpose"\r\n\r\n',
        purpose.encode(),
        b"\r\n",
        f"--{boundary}\r\n".encode(),
        (
            'Content-Disposition: form-data; name="file"; '
            f'filename="{fallback_filename}"; '
            f"filename*=UTF-8''{encoded_filename}\r\n"
        ).encode(),
        f"Content-Type: {mime_type}\r\n\r\n".encode(),
        path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks)


def _raise_for_api_error(response: dict[str, Any]) -> None:
    base_resp = response.get("base_resp")
    if not isinstance(base_resp, dict):
        raise MiniMaxError("MiniMax 响应缺少 base_resp")
    status_code = base_resp.get("status_code")
    if status_code != 0:
        status_msg = str(base_resp.get("status_msg", "unknown error"))
        raise MiniMaxError(f"MiniMax API 错误 {status_code}: {status_msg}")


def _safe_http_error_detail(error: urllib.error.HTTPError) -> str:
    try:
        response = json.loads(error.read().decode("utf-8"))
        base_resp = response.get("base_resp", {})
        detail = str(base_resp.get("status_msg") or response.get("message") or error.reason)
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        detail = str(error.reason)
    return detail[:500]


def _validate_audio(path_value: str, purpose: str) -> Path:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise MiniMaxError(f"音频文件不存在: {path}")
    if path.suffix.lower() not in {".mp3", ".m4a", ".wav"}:
        raise MiniMaxError("音频格式必须是 MP3、M4A 或 WAV")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise MiniMaxError("音频文件不能超过 20 MB")

    duration = _probe_duration_seconds(path)
    if duration is None:
        LOGGER.warning("event=duration_check status=skipped file=%s", path.name)
        return path
    if purpose == "voice_clone" and not 10 <= duration <= 300:
        raise MiniMaxError(f"复刻音频时长必须为 10–300 秒，当前约 {duration:.2f} 秒")
    if purpose == "prompt_audio" and not duration < 8:
        raise MiniMaxError(f"示例音频时长必须小于 8 秒，当前约 {duration:.2f} 秒")
    return path


def _probe_duration_seconds(path: Path) -> float | None:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as audio:
                return audio.getnframes() / audio.getframerate()
        except (wave.Error, ZeroDivisionError):
            return None
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _validate_voice_id(voice_id: str) -> None:
    if not VOICE_ID_PATTERN.fullmatch(voice_id):
        raise MiniMaxError(
            "voice_id 必须为 8–256 位，以英文字母开头，只含字母、数字、-、_，"
            "且不能以 - 或 _ 结尾"
        )


def _write_bytes(path_value: str, content: bytes) -> Path:
    path = Path(path_value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if path.stat().st_size == 0:
        raise MiniMaxError(f"输出文件为空: {path}")
    return path


def _write_json(path_value: str, payload: dict[str, Any]) -> Path:
    path = Path(path_value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _without_audio_payload(response: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(response)
    data = metadata.get("data")
    if isinstance(data, dict):
        metadata["data"] = {key: value for key, value in data.items() if key != "audio"}
    return metadata


def _read_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        text = args.text
    else:
        text = Path(args.text_file).expanduser().resolve().read_text(encoding="utf-8")
    if not text.strip():
        raise MiniMaxError("合成文本不能为空")
    if len(text) >= 10_000:
        raise MiniMaxError("同步合成文本必须少于 10,000 字符")
    if len(text) > 3_000:
        LOGGER.warning("event=long_text chars=%d recommendation=official_streaming_api", len(text))
    return text


def _load_local_env(path: Path) -> None:
    """Load supported settings without overriding process environment variables."""
    if not path.is_file():
        return
    if path.stat().st_mode & 0o077:
        LOGGER.warning("event=env_permissions status=insecure expected=600")
    supported_keys = {"MINIMAX_API_KEY", "MINIMAX_API_BASE", "MINIMAX_VOICE_ID"}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator:
            raise MiniMaxError(f"{path} 第 {line_number} 行不是 KEY=VALUE 格式")
        if key not in supported_keys:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key not in os.environ and value:
            os.environ[key] = value


def _build_client(args: argparse.Namespace) -> MiniMaxClient:
    _load_local_env(_bundle_env_path())
    api_key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not api_key:
        raise MiniMaxError("缺少环境变量 MINIMAX_API_KEY")
    api_base = os.environ.get("MINIMAX_API_BASE", DEFAULT_API_BASE).rstrip("/")
    if not api_base.startswith("https://"):
        raise MiniMaxError("MINIMAX_API_BASE 必须使用 https://")
    return MiniMaxClient(ClientConfig(api_key, api_base, args.timeout))


DEFAULT_VOICE_ID = "GuangxiLaoWang_Studio_20260814"


def _resolve_synthesis_voice_id(args: argparse.Namespace) -> None:
    if args.command != "synthesize" or args.voice_id:
        return
    args.voice_id = os.environ.get("MINIMAX_VOICE_ID", "").strip() or DEFAULT_VOICE_ID


def _command_upload(args: argparse.Namespace, client: MiniMaxClient) -> dict[str, Any]:
    path = _validate_audio(args.file, args.purpose)
    file_id = client.upload_file(path, args.purpose)
    return {"status": "ok", "purpose": args.purpose, "file_id": file_id}


def _command_clone(args: argparse.Namespace, client: MiniMaxClient) -> dict[str, Any]:
    if not args.confirm_rights:
        raise MiniMaxError("克隆前必须使用 --confirm-rights 确认已获得声音使用授权")
    _validate_voice_id(args.voice_id)
    if bool(args.prompt_audio) != bool(args.prompt_text):
        raise MiniMaxError("--prompt-audio 与 --prompt-text 必须同时提供")
    if bool(args.preview_text) != bool(args.preview_output):
        raise MiniMaxError("--preview-text 与 --preview-output 必须同时提供")
    if args.validation_text and len(args.validation_text) > 200:
        raise MiniMaxError("--validation-text 不能超过 200 字符")

    source_path = _validate_audio(args.source_audio, "voice_clone")
    LOGGER.info("event=clone_upload kind=source status=started")
    source_file_id = client.upload_file(source_path, "voice_clone")
    payload: dict[str, Any] = {
        "file_id": source_file_id,
        "voice_id": args.voice_id,
        "need_noise_reduction": args.noise_reduction,
        "need_volume_normalization": args.volume_normalization,
        "aigc_watermark": args.aigc_watermark,
    }
    if args.prompt_audio:
        prompt_path = _validate_audio(args.prompt_audio, "prompt_audio")
        LOGGER.info("event=clone_upload kind=prompt status=started")
        prompt_file_id = client.upload_file(prompt_path, "prompt_audio")
        payload["clone_prompt"] = {
            "prompt_audio": prompt_file_id,
            "prompt_text": args.prompt_text,
        }
    if args.validation_text:
        payload["text_validation"] = args.validation_text
        payload["accuracy"] = args.accuracy
    if args.preview_text:
        if len(args.preview_text) > 1_000:
            raise MiniMaxError("--preview-text 不能超过 1,000 字符")
        payload.update(
            {
                "text": args.preview_text,
                "model": MODEL,
                "language_boost": args.language_boost,
            }
        )

    LOGGER.info("event=voice_clone status=started voice_id=%s", args.voice_id)
    response = client.clone_voice(payload)
    if response.get("input_sensitive"):
        raise MiniMaxError("参考音频触发 MiniMax 风控，音色未按成功处理")
    result: dict[str, Any] = {
        "status": "ok",
        "voice_id": args.voice_id,
        "trace_id": response.get("trace_id"),
    }
    demo_audio = response.get("demo_audio")
    if args.preview_output and isinstance(demo_audio, str) and demo_audio:
        output = _write_bytes(args.preview_output, client.download(demo_audio))
        result["preview_output"] = str(output)
    return result


def _command_synthesize(args: argparse.Namespace, client: MiniMaxClient) -> dict[str, Any]:
    _validate_voice_id(args.voice_id)
    text = _read_text(args)
    output_path = Path(args.output).expanduser().resolve()
    audio_format = args.format or output_path.suffix.lower().lstrip(".") or "mp3"
    if audio_format not in {"mp3", "wav", "flac", "pcm"}:
        raise MiniMaxError("输出格式必须是 mp3、wav、flac 或 pcm")

    voice_setting: dict[str, Any] = {
        "voice_id": args.voice_id,
        "speed": args.speed,
        "vol": args.volume,
        "pitch": args.pitch,
    }
    if args.emotion:
        voice_setting["emotion"] = args.emotion
    payload: dict[str, Any] = {
        "model": MODEL,
        "text": text,
        "stream": False,
        "voice_setting": voice_setting,
        "audio_setting": {
            "sample_rate": args.sample_rate,
            "bitrate": args.bitrate,
            "format": audio_format,
            "channel": args.channel,
        },
        "language_boost": args.language_boost,
        "subtitle_enable": bool(args.subtitle_type),
        "output_format": "hex",
        "aigc_watermark": args.aigc_watermark,
    }
    if args.subtitle_type:
        payload["subtitle_type"] = args.subtitle_type

    LOGGER.info("event=synthesize status=started voice_id=%s chars=%d", args.voice_id, len(text))
    response = client.synthesize(payload)
    data = response.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("audio"), str):
        raise MiniMaxError("合成响应缺少 data.audio")
    try:
        audio = bytes.fromhex(data["audio"])
    except ValueError as exc:
        raise MiniMaxError("合成响应的音频不是有效十六进制数据") from exc
    output = _write_bytes(str(output_path), audio)
    if args.metadata_output:
        _write_json(args.metadata_output, _without_audio_payload(response))
    extra = response.get("extra_info") if isinstance(response.get("extra_info"), dict) else {}
    return {
        "status": "ok",
        "voice_id": args.voice_id,
        "output": str(output),
        "bytes": output.stat().st_size,
        "audio_length_ms": extra.get("audio_length"),
        "usage_characters": extra.get("usage_characters"),
        "trace_id": response.get("trace_id"),
        "metadata_output": str(Path(args.metadata_output).resolve()) if args.metadata_output else None,
    }


def _command_voices(args: argparse.Namespace, client: MiniMaxClient) -> dict[str, Any]:
    response = client.list_voices(args.type)
    return {
        "status": "ok",
        "voice_type": args.type,
        "system_voice": response.get("system_voice", []),
        "voice_cloning": response.get("voice_cloning", []),
        "voice_generation": response.get("voice_generation", []),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=120, help="HTTP 超时秒数")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upload = subparsers.add_parser("upload", help="上传复刻或示例音频")
    upload.add_argument("--purpose", choices=["voice_clone", "prompt_audio"], required=True)
    upload.add_argument("--file", required=True)

    clone = subparsers.add_parser("clone", help="上传音频并快速克隆音色")
    clone.add_argument("--source-audio", required=True)
    clone.add_argument("--voice-id", required=True)
    clone.add_argument("--prompt-audio")
    clone.add_argument("--prompt-text")
    clone.add_argument("--validation-text")
    clone.add_argument("--accuracy", type=float, default=0.7)
    clone.add_argument("--preview-text")
    clone.add_argument("--preview-output")
    clone.add_argument("--language-boost", default="auto")
    clone.add_argument("--noise-reduction", action="store_true")
    clone.add_argument("--volume-normalization", action="store_true")
    clone.add_argument("--aigc-watermark", action="store_true")
    clone.add_argument("--confirm-rights", action="store_true")

    synthesize = subparsers.add_parser("synthesize", help="使用克隆音色生成音频")
    synthesize.add_argument(
        "--voice-id",
        help="合成音色 ID（默认使用公司内部获授权的老王棚拍版，可由 MINIMAX_VOICE_ID 覆盖）",
    )
    text_group = synthesize.add_mutually_exclusive_group(required=True)
    text_group.add_argument("--text")
    text_group.add_argument("--text-file")
    synthesize.add_argument("--output", required=True)
    synthesize.add_argument("--format", choices=["mp3", "wav", "flac", "pcm"])
    synthesize.add_argument("--language-boost", default="auto")
    synthesize.add_argument("--speed", type=float, default=1.0)
    synthesize.add_argument("--volume", type=float, default=1.0)
    synthesize.add_argument("--pitch", type=int, default=0)
    synthesize.add_argument(
        "--emotion",
        choices=["happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm"],
    )
    synthesize.add_argument(
        "--sample-rate",
        type=int,
        choices=[8000, 16000, 22050, 24000, 32000, 44100],
        default=32000,
    )
    synthesize.add_argument(
        "--bitrate",
        type=int,
        choices=[32000, 64000, 128000, 256000],
        default=128000,
    )
    synthesize.add_argument("--channel", type=int, choices=[1, 2], default=1)
    synthesize.add_argument("--subtitle-type", choices=["sentence", "word"])
    synthesize.add_argument("--metadata-output")
    synthesize.add_argument("--aigc-watermark", action="store_true")

    voices = subparsers.add_parser("voices", help="查询账号可用音色")
    voices.add_argument(
        "--type",
        choices=["system", "voice_cloning", "voice_generation", "all"],
        default="all",
    )
    return parser


def _validate_numeric_arguments(args: argparse.Namespace) -> None:
    if args.timeout <= 0:
        raise MiniMaxError("--timeout 必须大于 0")
    if args.command == "clone" and not 0 <= args.accuracy <= 1:
        raise MiniMaxError("--accuracy 必须在 0–1 之间")
    if args.command == "synthesize":
        if not 0.5 <= args.speed <= 2:
            raise MiniMaxError("--speed 必须在 0.5–2 之间")
        if not 0 < args.volume <= 10:
            raise MiniMaxError("--volume 必须在 0–10 之间且不能为 0")
        if not -12 <= args.pitch <= 12:
            raise MiniMaxError("--pitch 必须在 -12–12 之间")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = _build_parser()
    args = parser.parse_args()
    try:
        _validate_numeric_arguments(args)
        client = _build_client(args)
        _resolve_synthesis_voice_id(args)
        handlers = {
            "upload": _command_upload,
            "clone": _command_clone,
            "synthesize": _command_synthesize,
            "voices": _command_voices,
        }
        result = handlers[args.command](args, client)
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return 0
    except (MiniMaxError, OSError, subprocess.SubprocessError, binascii.Error) as exc:
        LOGGER.error(
            "event=command_failed command=%s error_type=%s message=%s",
            args.command,
            type(exc).__name__,
            exc,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
