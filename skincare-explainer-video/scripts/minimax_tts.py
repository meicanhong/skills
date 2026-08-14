#!/usr/bin/env python3
"""Generate MiniMax narration and provider-neutral timeline metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def bundle_env_path() -> Path:
    configured = os.environ.get("SKINCARE_VIDEO_ENV", "").strip()
    return Path(configured).expanduser() if configured else codex_home() / "skincare-video-bundle.env"


MINIMAX_SKILL_ROOT = codex_home() / "skills" / "minimax-speech"
MINIMAX_SCRIPT = MINIMAX_SKILL_ROOT / "scripts" / "minimax_speech.py"
MINIMAX_ENV = bundle_env_path()
MODEL = "speech-2.8-hd"
DEFAULT_VOICE_ID = "GuangxiLaoWang_Studio_20260814"
DEFAULT_LANGUAGE_BOOST = "Chinese"


class ConfigurationError(RuntimeError):
    """Raised when the shared MiniMax skill or local runtime is unavailable."""


def _env_has_api_key(path: Path) -> bool:
    if os.environ.get("MINIMAX_API_KEY", "").strip():
        return True
    if not path.is_file():
        return False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, separator, value = line.partition("=")
        if separator and key.strip() == "MINIMAX_API_KEY" and value.strip().strip("'\""):
            return True
    return False


def resolve_voice_id(explicit_voice_id: str | None = None) -> str:
    if explicit_voice_id and explicit_voice_id.strip():
        return explicit_voice_id.strip()
    process_value = os.environ.get("MINIMAX_VOICE_ID", "").strip()
    if process_value:
        return process_value
    if MINIMAX_ENV.is_file():
        for raw_line in MINIMAX_ENV.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("export "):
                line = line.removeprefix("export ").strip()
            key, separator, value = line.partition("=")
            if separator and key.strip() == "MINIMAX_VOICE_ID":
                resolved = value.strip().strip("'\"")
                if resolved:
                    return resolved
    return DEFAULT_VOICE_ID


def check_runtime() -> None:
    if not MINIMAX_SCRIPT.is_file():
        raise ConfigurationError(f"MiniMax Skill 脚本不存在：{MINIMAX_SCRIPT}")
    if not _env_has_api_key(MINIMAX_ENV):
        raise ConfigurationError(f"MiniMax API Key 未配置：{MINIMAX_ENV}")
    if not shutil.which("ffprobe"):
        raise ConfigurationError("缺少命令：ffprobe")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MiniMax Speech 2.8 HD 旁白工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="只检查配置和本机依赖，不调用计费接口")

    synthesize = subparsers.add_parser("synthesize", help="生成完整旁白和非敏感元数据")
    source = synthesize.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="待合成文本")
    source.add_argument("--text-file", type=Path, help="UTF-8 旁白文件")
    synthesize.add_argument("--output", type=Path, required=True, help="输出 MP3 路径")
    synthesize.add_argument("--metadata", type=Path, required=True, help="非敏感生成元数据 JSON")
    synthesize.add_argument("--voice-id")
    synthesize.add_argument("--language-boost", default=DEFAULT_LANGUAGE_BOOST)
    synthesize.add_argument("--speed", type=float, default=1.0)
    synthesize.add_argument(
        "--emotion",
        choices=["happy", "sad", "angry", "fearful", "disgusted", "surprised", "calm"],
    )
    synthesize.add_argument("--sample-rate", type=int, default=44100)
    synthesize.add_argument("--bitrate", type=int, default=128000)
    synthesize.add_argument("--timeout", type=float, default=120.0)
    return parser


def read_text(args: argparse.Namespace) -> str:
    text = args.text if args.text is not None else args.text_file.read_text(encoding="utf-8")
    text = text.strip()
    if not text:
        raise ValueError("旁白文本不能为空")
    return text


def narration_sha256(text: str) -> str:
    """Fingerprint the exact trimmed text sent to MiniMax."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def probe_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return round(float(result.stdout.strip()), 3)


def build_minimax_command(
    args: argparse.Namespace, text: str, provider_metadata: Path
) -> list[str]:
    command = [
        sys.executable,
        str(MINIMAX_SCRIPT),
        "--timeout",
        str(args.timeout),
        "synthesize",
        "--voice-id",
        args.voice_id,
        "--text",
        text,
        "--output",
        str(args.output),
        "--format",
        "mp3",
        "--language-boost",
        args.language_boost,
        "--speed",
        str(args.speed),
        "--sample-rate",
        str(args.sample_rate),
        "--bitrate",
        str(args.bitrate),
        "--channel",
        "1",
        "--metadata-output",
        str(provider_metadata),
    ]
    if args.emotion:
        command.extend(["--emotion", args.emotion])
    return command


def synthesize(args: argparse.Namespace) -> dict[str, object]:
    text = read_text(args)
    args.voice_id = resolve_voice_id(args.voice_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="minimax-tts-") as temp_dir:
        provider_metadata_path = Path(temp_dir) / "provider.json"
        command = build_minimax_command(args, text, provider_metadata_path)
        result = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout + 30)
        if result.returncode != 0:
            message = result.stderr.strip() or "MiniMax 语音合成失败"
            raise RuntimeError(message[-1000:])
        try:
            provider_result = json.loads(result.stdout)
            provider_metadata = json.loads(provider_metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            raise RuntimeError("MiniMax 成功响应缺少有效元数据") from error

    if not args.output.is_file() or args.output.stat().st_size == 0:
        raise RuntimeError("接口返回成功，但没有生成有效音频")

    metadata: dict[str, object] = {
        "provider": "minimax",
        "model": MODEL,
        "voice_id": args.voice_id,
        "language_boost": args.language_boost,
        "speed": args.speed,
        "emotion": args.emotion,
        "format": "mp3",
        "sample_rate": args.sample_rate,
        "bitrate": args.bitrate,
        "channel": 1,
        "audio_path": str(args.output.resolve()),
        "audio_bytes": args.output.stat().st_size,
        "duration_s": probe_duration(args.output),
        "usage_characters": provider_result.get("usage_characters"),
        "trace_id": provider_result.get("trace_id") or provider_metadata.get("trace_id"),
        "narration_sha256": narration_sha256(text),
    }
    args.metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def main() -> int:
    args = build_parser().parse_args()
    try:
        check_runtime()
        if args.command == "check":
            voice_id = resolve_voice_id()
            print(
                json.dumps(
                    {
                        "ok": True,
                        "provider": "minimax",
                        "model": MODEL,
                        "voice_id": voice_id,
                        "api_key_present": True,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        metadata = synthesize(args)
        print(json.dumps(metadata, ensure_ascii=False))
        return 0
    except (
        ConfigurationError,
        ValueError,
        RuntimeError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
