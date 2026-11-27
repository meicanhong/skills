#!/usr/bin/env python3
"""Align canonical narration with normalized ASR timestamps and emit timeline/SRT/ASS."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import unicodedata


MIN_SCENE_SECONDS = 0.35
MAX_SCENE_SECONDS = 8.0
MIN_SEEDANCE_DURATION_SECONDS = 4
MAX_SEEDANCE_DURATION_SECONDS = 15
MAX_SUBTITLE_CHARS = 15
PREFERRED_SUBTITLE_CHARS = 8
ASR_EDIT_WARNING_RATIO = 0.05
MAX_ASR_EDIT_RATIO = 0.1
REQUIRED_TIMESTAMP_SOURCE = "aliyun_fun_asr_flash"
BREAK_PUNCTUATION = set("，。！？；：,.!?;:")


class TimelineError(RuntimeError):
    pass


def normalize_text(text: str) -> str:
    return "".join(
        char.casefold()
        for char in unicodedata.normalize("NFKC", text)
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TimelineError(f"无法读取 JSON {path}: {error}") from error


def load_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise TimelineError(f"无法读取旁白 {path}: {error}") from error
    if not text:
        raise TimelineError("旁白文件不能为空")
    return text


def narration_sha256(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def narration_contract_text(text: str) -> str:
    """Ignore paragraph whitespace while preserving every spoken symbol."""
    return "".join(character for character in text if not character.isspace())


def validate_narration_contract(
    scenes: list[dict[str, object]], narration: str, tts_metadata: object
) -> str:
    if not isinstance(tts_metadata, dict):
        raise TimelineError("TTS 元数据必须是 JSON 对象")
    recorded_hash = tts_metadata.get("narration_sha256")
    actual_hash = narration_sha256(narration)
    if not isinstance(recorded_hash, str) or recorded_hash != actual_hash:
        raise TimelineError("旁白文件与 TTS 实际合成文本的 SHA-256 不一致")
    storyboard_text = "".join(str(scene["narration"]) for scene in scenes)
    if narration_contract_text(storyboard_text) != narration_contract_text(narration):
        raise TimelineError("分镜 narration 与 TTS 实际合成旁白不一致")
    return actual_hash


def extract_scenes(document: object) -> tuple[list[dict[str, object]], str | None]:
    if isinstance(document, list):
        scenes = document
        container_key = None
    elif isinstance(document, dict) and isinstance(document.get("scenes"), list):
        scenes = document["scenes"]
        container_key = "scenes"
    else:
        raise TimelineError("分镜 JSON 必须是数组，或包含 scenes 数组的对象")

    if not scenes:
        raise TimelineError("分镜不能为空")
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            raise TimelineError(f"第 {index} 个镜头不是对象")
        narration = scene.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            raise TimelineError(f"第 {index} 个镜头缺少非空 narration")
    return scenes, container_key


def extract_asr_words(document: object) -> tuple[list[dict[str, object]], str]:
    if not isinstance(document, dict) or not isinstance(document.get("segments"), list):
        raise TimelineError("ASR JSON 必须包含 segments 数组")

    raw_words = [
        item
        for segment in document["segments"]
        if isinstance(segment, dict) and isinstance(segment.get("words"), list)
        for item in segment["words"]
    ]
    if not raw_words:
        raise TimelineError("ASR JSON 不包含词级时间戳")

    metadata = document.get("metadata")
    source = (
        str(metadata.get("timestamp_source"))
        if isinstance(metadata, dict) and metadata.get("timestamp_source")
        else ""
    )
    if source != REQUIRED_TIMESTAMP_SOURCE:
        raise TimelineError(
            "生产时间轴只接受阿里云 Fun-ASR 输出"
            f"（timestamp_source 必须为 {REQUIRED_TIMESTAMP_SOURCE}）"
        )

    previous_end = 0.0
    words: list[dict[str, object]] = []
    for index, item in enumerate(raw_words, start=1):
        if not isinstance(item, dict):
            raise TimelineError(f"第 {index} 个时间戳不是对象")
        word = item.get("word")
        start = item.get("start")
        end = item.get("end")
        if not isinstance(word, str) or not word.strip():
            raise TimelineError(f"第 {index} 个 ASR 时间戳缺少有效 word")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise TimelineError(f"第 {index} 个 ASR 时间戳缺少数值 start/end")
        start_value, end_value = float(start), float(end)
        if start_value < 0 or end_value <= start_value or start_value + 0.001 < previous_end:
            raise TimelineError(f"第 {index} 个 ASR 时间戳不单调或时长无效")
        previous_end = end_value
        # Fun-ASR 会把中文标点作为独立的词级时间戳返回。标点不参与
        # 字符对齐，但仍需先通过上面的时间轴校验，避免掩盖乱序数据。
        if not normalize_text(word):
            continue
        words.append({"word": word, "startTime": start_value, "endTime": end_value})
    return words, source


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
        raise TimelineError(f"无法读取音频时长：{error}") from error
    if duration <= 0:
        raise TimelineError("音频时长必须大于 0")
    return duration


def expand_asr_characters(words: list[dict[str, object]]) -> list[dict[str, object]]:
    characters: list[dict[str, object]] = []
    for item in words:
        text = normalize_text(str(item["word"]))
        start = float(item["startTime"])
        end = float(item["endTime"])
        step = (end - start) / len(text)
        for index, character in enumerate(text):
            characters.append(
                {
                    "word": character,
                    "startTime": start + step * index,
                    "endTime": start + step * (index + 1),
                }
            )
    return characters


def align_expected_characters(
    expected_text: str, asr_characters: list[dict[str, object]]
) -> tuple[list[dict[str, object]], float]:
    recognized_text = "".join(str(item["word"]) for item in asr_characters)
    rows, columns = len(expected_text) + 1, len(recognized_text) + 1
    costs = [[0] * columns for _ in range(rows)]
    moves = [[""] * columns for _ in range(rows)]
    for row in range(1, rows):
        costs[row][0], moves[row][0] = row, "delete"
    for column in range(1, columns):
        costs[0][column], moves[0][column] = column, "insert"

    for row in range(1, rows):
        for column in range(1, columns):
            candidates = (
                (costs[row - 1][column - 1] + (expected_text[row - 1] != recognized_text[column - 1]), "diagonal"),
                (costs[row - 1][column] + 1, "delete"),
                (costs[row][column - 1] + 1, "insert"),
            )
            costs[row][column], moves[row][column] = min(candidates, key=lambda item: item[0])

    edit_ratio = costs[-1][-1] / max(len(expected_text), len(recognized_text))
    if edit_ratio > MAX_ASR_EDIT_RATIO:
        raise TimelineError(
            f"ASR 正文与已确认旁白差异过大（编辑率 {edit_ratio:.1%} > {MAX_ASR_EDIT_RATIO:.0%}）"
        )

    mapping: list[int | None] = [None] * len(expected_text)
    row, column = len(expected_text), len(recognized_text)
    while row or column:
        move = moves[row][column]
        if move == "diagonal":
            mapping[row - 1] = column - 1
            row -= 1
            column -= 1
        elif move == "delete":
            row -= 1
        elif move == "insert":
            column -= 1
        else:
            raise TimelineError("ASR 字符对齐失败")

    mapped_indices = [index for index, value in enumerate(mapping) if value is not None]
    if not mapped_indices:
        raise TimelineError("ASR 字符对齐未找到任何有效映射")
    for index, value in enumerate(mapping):
        if value is not None:
            continue
        next_index = next((candidate for candidate in mapped_indices if candidate > index), None)
        previous_index = next((candidate for candidate in reversed(mapped_indices) if candidate < index), None)
        source_index = next_index if next_index is not None else previous_index
        assert source_index is not None and mapping[source_index] is not None
        mapping[index] = mapping[source_index]

    canonical_characters = []
    for character, source_index in zip(expected_text, mapping):
        assert source_index is not None
        source = asr_characters[source_index]
        canonical_characters.append({**source, "word": character})
    return canonical_characters, edit_ratio


def restore_canonical_text(
    scenes: list[dict[str, object]], canonical_characters: list[dict[str, object]]
) -> list[dict[str, object]]:
    restored: list[dict[str, object]] = []
    cursor = 0
    for scene in scenes:
        scene_characters: list[dict[str, object]] = []
        pending_prefix = ""
        for character in str(scene["narration"]):
            normalized = normalize_text(character)
            if not normalized:
                if character.isspace():
                    continue
                if scene_characters:
                    scene_characters[-1]["word"] = str(scene_characters[-1]["word"]) + character
                else:
                    pending_prefix += character
                continue
            for normalized_index, _ in enumerate(normalized):
                if cursor >= len(canonical_characters):
                    raise TimelineError("恢复旁白文字时超出 ASR 对齐范围")
                restored_character = copy.deepcopy(canonical_characters[cursor])
                restored_character["word"] = (
                    pending_prefix + character if normalized_index == 0 else ""
                )
                pending_prefix = ""
                scene_characters.append(restored_character)
                cursor += 1
        if pending_prefix and scene_characters:
            scene_characters[-1]["word"] = str(scene_characters[-1]["word"]) + pending_prefix
        restored.extend(scene_characters)
    if cursor != len(canonical_characters):
        raise TimelineError("恢复旁白文字后仍有未消费的 ASR 对齐字符")
    return restored


def align_scenes(
    scenes: list[dict[str, object]], words: list[dict[str, object]], audio_duration: float
) -> tuple[list[tuple[int, int]], list[dict[str, object]], float]:
    scene_texts = [normalize_text(str(scene["narration"])) for scene in scenes]
    expected_text = "".join(scene_texts)
    canonical_characters, edit_ratio = align_expected_characters(expected_text, expand_asr_characters(words))
    canonical_characters = restore_canonical_text(scenes, canonical_characters)

    boundaries = [0]
    for text in scene_texts:
        boundaries.append(boundaries[-1] + len(text))
    word_ranges = list(zip(boundaries[:-1], boundaries[1:]))

    starts = [0.0]
    starts.extend(float(canonical_characters[start]["startTime"]) for start, _ in word_ranges[1:])
    ends = starts[1:] + [audio_duration]
    for index, (start, end) in enumerate(zip(starts, ends), start=1):
        duration = end - start
        if duration < MIN_SCENE_SECONDS:
            raise TimelineError(f"镜头 {index} 真实时长仅 {duration:.3f}s，短于可用阈值")
        if duration > MAX_SCENE_SECONDS:
            raise TimelineError(f"镜头 {index} 真实时长 {duration:.3f}s，超过 8 秒；必须拆镜头")
    return word_ranges, canonical_characters, edit_ratio


def scene_times(
    word_ranges: list[tuple[int, int]], words: list[dict[str, object]], audio_duration: float
) -> list[tuple[float, float]]:
    starts = [0.0]
    starts.extend(float(words[start]["startTime"]) for start, _ in word_ranges[1:])
    return list(zip(starts, starts[1:] + [audio_duration]))


def visible_length(text: str) -> int:
    return len(normalize_text(text))


def subtitle_groups(word_slice: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    groups: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    current_length = 0
    for item in word_slice:
        token = str(item["word"])
        token_length = visible_length(token)
        if current and current_length + token_length > MAX_SUBTITLE_CHARS:
            groups.append(current)
            current = []
            current_length = 0
        current.append(item)
        current_length += token_length
        if current_length >= PREFERRED_SUBTITLE_CHARS and any(char in BREAK_PUNCTUATION for char in token):
            groups.append(current)
            current = []
            current_length = 0
    if current:
        groups.append(current)
    return groups


def build_cues(
    word_ranges: list[tuple[int, int]], words: list[dict[str, object]]
) -> list[dict[str, object]]:
    cues: list[dict[str, object]] = []
    for scene_index, (word_start, word_end) in enumerate(word_ranges, start=1):
        for group in subtitle_groups(words[word_start:word_end]):
            text = "".join(str(item["word"]) for item in group).strip()
            cues.append(
                {
                    "scene": scene_index,
                    "start": float(group[0]["startTime"]),
                    "end": float(group[-1]["endTime"]),
                    "text": text,
                }
            )
    return cues


def srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def ass_time(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def write_srt(path: Path, cues: list[dict[str, object]]) -> None:
    blocks = [
        f"{index}\n{srt_time(float(cue['start']))} --> {srt_time(float(cue['end']))}\n{cue['text']}"
        for index, cue in enumerate(cues, start=1)
    ]
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def write_ass(path: Path, cues: list[dict[str, object]], aspect_ratio: str) -> None:
    if aspect_ratio == "9:16":
        width, height, font_size, margin_v = 1080, 1920, 64, 300
    else:
        width, height, font_size, margin_v = 1920, 1080, 54, 100
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,PingFang SC,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,1,2,90,160,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [
        "Dialogue: 0,"
        f"{ass_time(float(cue['start']))},{ass_time(float(cue['end']))},"
        f"Default,,0,0,0,,{escape_ass(str(cue['text']))}"
        for cue in cues
    ]
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def update_storyboard(
    document: object,
    scenes: list[dict[str, object]],
    container_key: str | None,
    times: list[tuple[float, float]],
    audio_duration: float,
    timestamp_source: str,
    aspect_ratio: str,
) -> object:
    updated_scenes = []
    for index, (scene, (start, end)) in enumerate(zip(scenes, times), start=1):
        updated = copy.deepcopy(scene)
        updated["scene"] = updated.get("scene", index)
        updated["start_s"] = round(start, 3)
        updated["end_s"] = round(end, 3)
        updated["duration_s"] = round(end - start, 3)
        seedance_duration = max(MIN_SEEDANCE_DURATION_SECONDS, math.ceil(end - start))
        if seedance_duration > MAX_SEEDANCE_DURATION_SECONDS:
            raise TimelineError(
                f"镜头 {index} 需要提交 {seedance_duration} 秒，超过 Seedance 2.0 Mini "
                f"上限 {MAX_SEEDANCE_DURATION_SECONDS} 秒；必须拆镜头"
            )
        updated["seedance_duration_s"] = seedance_duration
        updated["timestamp_source"] = timestamp_source
        updated_scenes.append(updated)

    if container_key is None:
        return updated_scenes
    updated_document = copy.deepcopy(document)
    assert isinstance(updated_document, dict)
    updated_document[container_key] = updated_scenes
    updated_document["audio_duration_s"] = round(audio_duration, 3)
    updated_document["timeline_source"] = timestamp_source
    updated_document["aspect_ratio"] = aspect_ratio
    return updated_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="阿里云 Fun-ASR 真实时间戳到分镜与字幕")
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--narration-file", type=Path, required=True)
    parser.add_argument("--tts-metadata", type=Path, required=True)
    parser.add_argument("--asr-json", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--ass", type=Path, required=True)
    parser.add_argument(
        "--aspect-ratio", choices=("9:16", "16:9"), default="9:16"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        storyboard_document = load_json(args.storyboard)
        scenes, container_key = extract_scenes(storyboard_document)
        narration_hash = validate_narration_contract(
            scenes,
            load_text(args.narration_file),
            load_json(args.tts_metadata),
        )
        words, timestamp_source = extract_asr_words(load_json(args.asr_json))
        audio_duration = probe_duration(args.audio)
        if float(words[-1]["endTime"]) > audio_duration + 0.1:
            raise TimelineError("最后一个字词时间戳超过音频时长")
        word_ranges, canonical_characters, edit_ratio = align_scenes(scenes, words, audio_duration)
        times = scene_times(word_ranges, canonical_characters, audio_duration)
        cues = build_cues(word_ranges, canonical_characters)
        for path in (args.timeline, args.srt, args.ass):
            path.parent.mkdir(parents=True, exist_ok=True)
        updated = update_storyboard(
            storyboard_document,
            scenes,
            container_key,
            times,
            audio_duration,
            timestamp_source,
            args.aspect_ratio,
        )
        if isinstance(updated, dict):
            updated["narration_sha256"] = narration_hash
        args.timeline.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_srt(args.srt, cues)
        write_ass(args.ass, cues, args.aspect_ratio)
        print(
            json.dumps(
                {
                    "ok": True,
                    "scenes": len(scenes),
                    "subtitle_cues": len(cues),
                    "asr_edit_ratio": round(edit_ratio, 4),
                    "asr_quality_warning": edit_ratio > ASR_EDIT_WARNING_RATIO,
                    "narration_sha256": narration_hash,
                    "timestamp_source": timestamp_source,
                    "audio_duration_s": round(audio_duration, 3),
                    "aspect_ratio": args.aspect_ratio,
                    "timeline": str(args.timeline.resolve()),
                    "srt": str(args.srt.resolve()),
                    "ass": str(args.ass.resolve()),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except TimelineError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
