#!/usr/bin/env python3
"""Generate Doubao V3 narration without exposing credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


SKILL_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = SKILL_ROOT / ".env"
SEEDAUDIO_PACKAGE = "zjandrew-seedaudio-cli==1.0.1"
REQUIRED_KEYS = (
    "DOUBAO_TTS_API_KEY",
    "DOUBAO_TTS_RESOURCE_ID",
    "DOUBAO_TTS_SPEAKER",
    "DOUBAO_TTS_MODEL",
)


class ConfigurationError(RuntimeError):
    pass


def load_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ConfigurationError(f"配置文件不存在：{path}")

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    missing = [key for key in REQUIRED_KEYS if not values.get(key)]
    if missing:
        raise ConfigurationError("缺少配置项：" + ", ".join(missing))
    return values


def check_runtime() -> None:
    missing = [command for command in ("uvx", "ffprobe") if not shutil.which(command)]
    if missing:
        raise ConfigurationError("缺少命令：" + ", ".join(missing))


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
    )
    return round(float(result.stdout.strip()), 3)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="豆包语音 V3 复刻音色旁白工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="只检查配置和本机依赖，不调用计费接口")

    synthesize = subparsers.add_parser("synthesize", help="生成旁白和字词时间戳")
    source = synthesize.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="待合成文本")
    source.add_argument("--text-file", type=Path, help="UTF-8 旁白文件")
    synthesize.add_argument("--output", type=Path, required=True, help="输出音频路径")
    synthesize.add_argument("--words", type=Path, required=True, help="字词时间戳 JSON")
    synthesize.add_argument("--metadata", type=Path, required=True, help="非敏感生成元数据 JSON")
    synthesize.add_argument("--instruction", required=True, help="TTS 2.0 表演指令")
    synthesize.add_argument("--speech-rate", type=int, help="语速，范围 -50 到 100")
    synthesize.add_argument("--resource-id", help="覆盖配置中的 Resource ID")
    synthesize.add_argument("--speaker", help="覆盖配置中的音色 ID")
    synthesize.add_argument("--model", help="覆盖配置中的模型")
    synthesize.add_argument("--timeout", type=float, default=120.0)
    return parser


def read_text(args: argparse.Namespace) -> str:
    text = args.text if args.text is not None else args.text_file.read_text(encoding="utf-8")
    text = text.strip()
    if not text:
        raise ValueError("旁白文本不能为空")
    return text


def narration_sha256(text: str) -> str:
    """Fingerprint the exact trimmed text sent to the TTS provider."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def synthesize(args: argparse.Namespace, config: dict[str, str]) -> None:
    text = read_text(args)
    resource_id = args.resource_id or config["DOUBAO_TTS_RESOURCE_ID"]
    speaker = args.speaker or config["DOUBAO_TTS_SPEAKER"]
    model = args.model or config["DOUBAO_TTS_MODEL"]
    speech_rate = args.speech_rate
    if speech_rate is None:
        speech_rate = int(config.get("DOUBAO_TTS_SPEECH_RATE", "0"))
    if not -50 <= speech_rate <= 100:
        raise ValueError("speech-rate 必须在 -50 到 100 之间")

    for output_path in (args.output, args.words, args.metadata):
        output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "uvx",
        "--from",
        SEEDAUDIO_PACKAGE,
        "seedaudio-cli",
        "--resource-id",
        resource_id,
        "--format",
        "json",
        "synthesize",
        "--text",
        text,
        "--speaker",
        speaker,
        "--model",
        model,
        "--encoding",
        config.get("DOUBAO_TTS_FORMAT", "mp3"),
        "--sample-rate",
        config.get("DOUBAO_TTS_SAMPLE_RATE", "24000"),
        "--speech-rate",
        str(speech_rate),
        "--subtitle",
        "--instruct",
        args.instruction,
        "--out",
        str(args.output),
        "--out-subtitle",
        str(args.words),
        "--timeout",
        str(args.timeout),
    ]

    child_env = os.environ.copy()
    child_env["SEEDAUDIO_API_KEY"] = config["DOUBAO_TTS_API_KEY"]
    result = subprocess.run(command, env=child_env, capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or "豆包语音合成失败"
        raise RuntimeError(message)

    if not args.output.is_file() or args.output.stat().st_size == 0:
        raise RuntimeError("接口返回成功，但没有生成有效音频")
    if not args.words.is_file():
        raise RuntimeError("接口未生成字幕时间戳")

    words = json.loads(args.words.read_text(encoding="utf-8"))
    duration = probe_duration(args.output)
    metadata = {
        "audio_path": str(args.output.resolve()),
        "words_path": str(args.words.resolve()),
        "duration_s": duration,
        "word_count": len(words),
        "resource_id": resource_id,
        "model": model,
        "format": config.get("DOUBAO_TTS_FORMAT", "mp3"),
        "sample_rate": int(config.get("DOUBAO_TTS_SAMPLE_RATE", "24000")),
        "speech_rate": speech_rate,
        "narration_sha256": narration_sha256(text),
    }
    args.metadata.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_env(ENV_PATH)
        check_runtime()
        if args.command == "check":
            print(
                json.dumps(
                    {
                        "ok": True,
                        "api_key_present": True,
                        "speaker_present": True,
                        "resource_id": config["DOUBAO_TTS_RESOURCE_ID"],
                        "model": config["DOUBAO_TTS_MODEL"],
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        synthesize(args, config)
        return 0
    except (ConfigurationError, ValueError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
