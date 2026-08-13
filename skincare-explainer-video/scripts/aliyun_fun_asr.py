#!/usr/bin/env python3
"""Call Alibaba Cloud Fun-ASR-Flash and emit normalized word timestamps."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request


DEFAULT_MODEL = "fun-asr-flash-2026-06-15"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
MAX_DATA_URI_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 300.0


class AsrError(RuntimeError):
    pass


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_config(env_path: Path) -> dict[str, str]:
    file_values = load_env(env_path)

    def value(name: str, default: str = "") -> str:
        return os.environ.get(name) or file_values.get(name) or default

    return {
        "api_key": value("DASHSCOPE_API_KEY"),
        "base_url": value("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL),
        "model": DEFAULT_MODEL,
    }


def probe_duration(audio_path: Path) -> float:
    try:
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
        duration = float(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise AsrError(f"无法读取音频时长：{error}") from error
    if duration <= 0 or duration > MAX_AUDIO_SECONDS:
        raise AsrError(f"音频时长必须在 0–{MAX_AUDIO_SECONDS:.0f} 秒内，当前 {duration:.3f} 秒")
    return duration


def validate_audio(audio_path: Path) -> tuple[float, str]:
    if not audio_path.is_file():
        raise AsrError(f"音频不存在：{audio_path}")
    size = audio_path.stat().st_size
    encoded_size = ((size + 2) // 3) * 4
    if size <= 0 or encoded_size > MAX_DATA_URI_BYTES:
        raise AsrError(
            f"音频 Base64 编码后必须不超过 10MB，当前预计 {encoded_size} 字节"
        )
    mime_type = mimetypes.guess_type(audio_path.name)[0]
    if mime_type not in {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav"}:
        raise AsrError("当前客户端仅接受 MP3 或 WAV 音频")
    return probe_duration(audio_path), "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"


def build_payload(
    audio_path: Path,
    mime_type: str,
    model: str,
    context: str | None,
) -> dict[str, object]:
    data_uri = f"data:{mime_type};base64,{base64.b64encode(audio_path.read_bytes()).decode('ascii')}"
    messages: list[dict[str, object]] = []
    if context:
        messages.extend(
            [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "请按已确认的中文旁白准确识别。"}],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": context}],
                },
            ]
        )
    messages.append(
        {
            "role": "user",
            "content": [{"type": "input_audio", "input_audio": {"data": data_uri}}],
        }
    )
    return {
        "model": model,
        "input": {"messages": messages},
        "parameters": {
            "format": "mp3" if mime_type == "audio/mpeg" else "wav",
            "language_hints": ["zh"],
        },
    }


def request_asr(url: str, api_key: str, payload: dict[str, object], timeout: float) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-SSE": "disable",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            document = json.loads(body)
            message = document.get("message") or document.get("code") or f"HTTP {error.code}"
        except json.JSONDecodeError:
            message = f"HTTP {error.code}"
        raise AsrError(f"阿里云 ASR 请求失败：{message}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise AsrError(f"阿里云 ASR 网络或响应错误：{error}") from error


def normalize_response(document: object, duration: float, model: str) -> dict[str, object]:
    if not isinstance(document, dict):
        raise AsrError("阿里云响应必须是 JSON 对象")
    output = document.get("output")
    if not isinstance(output, dict):
        raise AsrError("阿里云响应缺少 output")
    raw_sentences = output.get("sentences")
    if not isinstance(raw_sentences, list):
        sentence = output.get("sentence")
        raw_sentences = [sentence] if isinstance(sentence, dict) else []
    if not raw_sentences:
        raise AsrError("阿里云响应缺少句级结果")

    segments: list[dict[str, object]] = []
    previous_end = 0.0
    for index, sentence in enumerate(raw_sentences):
        if not isinstance(sentence, dict) or not isinstance(sentence.get("words"), list):
            raise AsrError(f"第 {index + 1} 句缺少 words 时间戳")
        words: list[dict[str, object]] = []
        for raw_word in sentence["words"]:
            if not isinstance(raw_word, dict):
                raise AsrError("阿里云 words 项必须是对象")
            text = raw_word.get("text")
            begin = raw_word.get("begin_time")
            end = raw_word.get("end_time")
            if not isinstance(text, str) or not text.strip():
                raise AsrError("阿里云 word 缺少有效 text")
            if not isinstance(begin, (int, float)) or not isinstance(end, (int, float)):
                raise AsrError("阿里云 word 缺少 begin_time/end_time")
            start_seconds, end_seconds = float(begin) / 1000, float(end) / 1000
            if start_seconds + 0.001 < previous_end or end_seconds <= start_seconds:
                raise AsrError("阿里云 word 时间戳不单调或时长无效")
            previous_end = end_seconds
            words.append({"word": text, "start": start_seconds, "end": end_seconds})
        segments.append(
            {
                "id": index,
                "start": words[0]["start"],
                "end": words[-1]["end"],
                "text": str(sentence.get("text") or "".join(str(word["word"]) for word in words)),
                "words": words,
            }
        )
    return {
        "text": str(output.get("text") or "".join(str(segment["text"]) for segment in segments)),
        "segments": segments,
        "metadata": {
            "timestamp_source": "aliyun_fun_asr_flash",
            "model": model,
            "audio_duration_s": round(duration, 3),
            "request_id": document.get("request_id"),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="阿里云 Fun-ASR-Flash 真实词级时间戳")
    parser.add_argument("command", choices=("check", "transcribe"))
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--context-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).parents[1] / ".env")
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = resolve_config(args.env_file)
        if args.command == "check":
            print(
                json.dumps(
                    {
                        "ok": bool(config["api_key"]),
                        "api_key_present": bool(config["api_key"]),
                        "model": config["model"],
                        "base_url_configured": bool(config["base_url"]),
                    },
                    ensure_ascii=False,
                )
            )
            return 0 if config["api_key"] else 1
        if not config["api_key"]:
            raise AsrError("缺少 DASHSCOPE_API_KEY；请配置在 Skill .env 或进程环境中")
        if args.audio is None or args.output is None:
            raise AsrError("transcribe 必须提供 --audio 和 --output")
        duration, mime_type = validate_audio(args.audio)
        context = args.context_file.read_text(encoding="utf-8").strip() if args.context_file else None
        response = request_asr(
            config["base_url"],
            config["api_key"],
            build_payload(args.audio, mime_type, config["model"], context),
            args.timeout,
        )
        normalized = normalize_response(response, duration, config["model"])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        word_count = sum(len(segment["words"]) for segment in normalized["segments"])
        print(
            json.dumps(
                {
                    "ok": True,
                    "model": config["model"],
                    "word_count": word_count,
                    "audio_duration_s": round(duration, 3),
                    "output": str(args.output.resolve()),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (AsrError, OSError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
