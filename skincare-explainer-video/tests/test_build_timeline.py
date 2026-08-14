from __future__ import annotations

import importlib.util
from pathlib import Path
import hashlib
import tempfile
import unittest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_timeline.py"
SPEC = importlib.util.spec_from_file_location("build_timeline", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BuildTimelineTests(unittest.TestCase):
    def test_seedance_duration_never_falls_below_four_seconds(self) -> None:
        document = [{"narration": "短镜头"}]

        updated = MODULE.update_storyboard(
            document,
            document,
            None,
            [(0.0, 3.0)],
            3.0,
            MODULE.REQUIRED_TIMESTAMP_SOURCE,
            "9:16",
        )

        self.assertEqual(updated[0]["duration_s"], 3.0)
        self.assertEqual(updated[0]["seedance_duration_s"], 4)

    def test_reads_aliyun_normalized_source(self) -> None:
        document = {
            "segments": [
                {
                    "words": [
                        {"word": "大家好", "start": 1.5, "end": 1.8},
                    ]
                }
            ],
            "metadata": {"timestamp_source": "aliyun_fun_asr_flash"},
        }

        words, source = MODULE.extract_asr_words(document)

        self.assertEqual(source, "aliyun_fun_asr_flash")
        self.assertEqual(words[0]["startTime"], 1.5)

    def test_ignores_standalone_punctuation_timestamp(self) -> None:
        document = {
            "segments": [
                {
                    "words": [
                        {"word": "真相", "start": 1.0, "end": 1.3},
                        {"word": "：", "start": 1.3, "end": 1.4},
                        {"word": "痘痘", "start": 1.4, "end": 1.7},
                    ]
                }
            ],
            "metadata": {"timestamp_source": "aliyun_fun_asr_flash"},
        }

        words, _ = MODULE.extract_asr_words(document)

        self.assertEqual([item["word"] for item in words], ["真相", "痘痘"])

    def test_fun_asr_time_with_canonical_text(self) -> None:
        scenes = [
            {"narration": "多吃抗炎食物，是可以消痘的。"},
            {"narration": "大家好，我是小医。"},
        ]
        asr_words = [
            {"word": "多吃抗炎食物是可以消痘的", "startTime": 0.0, "endTime": 1.0},
            {"word": "大家好", "startTime": 1.5, "endTime": 1.8},
            {"word": "我是小一", "startTime": 1.8, "endTime": 2.4},
        ]

        ranges, canonical, edit_ratio = MODULE.align_scenes(scenes, asr_words, 2.6)
        times = MODULE.scene_times(ranges, canonical, 2.6)
        cues = MODULE.build_cues(ranges, canonical)

        self.assertLess(edit_ratio, MODULE.MAX_ASR_EDIT_RATIO)
        self.assertEqual(times[1][0], 1.5)
        self.assertEqual(
            "".join(cue["text"] for cue in cues),
            "多吃抗炎食物，是可以消痘的。大家好，我是小医。",
        )

    def test_rejects_large_transcript_difference(self) -> None:
        scenes = [{"narration": "这是完全不同的旁白。"}]
        asr_words = [{"word": "天气晴朗", "startTime": 0.0, "endTime": 1.0}]

        with self.assertRaisesRegex(MODULE.TimelineError, "差异过大"):
            MODULE.align_scenes(scenes, asr_words, 1.2)

    def test_rejects_non_aliyun_timestamp_source(self) -> None:
        document = {
            "segments": [
                {"words": [{"word": "大家好", "start": 0.0, "end": 0.5}]}
            ],
            "metadata": {"timestamp_source": "mlx_whisper_word_timestamps"},
        }

        with self.assertRaisesRegex(MODULE.TimelineError, "只接受阿里云 Fun-ASR"):
            MODULE.extract_asr_words(document)

    def test_validates_exact_tts_narration_contract(self) -> None:
        narration = "第一句。\n\n第二句！"
        scenes = [{"narration": "第一句。"}, {"narration": "第二句！"}]
        metadata = {
            "narration_sha256": hashlib.sha256(narration.encode("utf-8")).hexdigest()
        }

        result = MODULE.validate_narration_contract(scenes, narration, metadata)

        self.assertEqual(result, metadata["narration_sha256"])

    def test_rejects_storyboard_text_different_from_tts(self) -> None:
        narration = "大家好，我是小医。"
        metadata = {
            "narration_sha256": hashlib.sha256(narration.encode("utf-8")).hexdigest()
        }

        with self.assertRaisesRegex(MODULE.TimelineError, "分镜 narration"):
            MODULE.validate_narration_contract(
                [{"narration": "大家好，我是小一。"}], narration, metadata
            )

    def test_rejects_tts_metadata_hash_mismatch(self) -> None:
        with self.assertRaisesRegex(MODULE.TimelineError, "SHA-256"):
            MODULE.validate_narration_contract(
                [{"narration": "大家好。"}],
                "大家好。",
                {"narration_sha256": "invalid"},
            )

    def test_ass_canvas_follows_aspect_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            portrait = Path(directory) / "portrait.ass"
            landscape = Path(directory) / "landscape.ass"
            MODULE.write_ass(portrait, [], "9:16")
            MODULE.write_ass(landscape, [], "16:9")

            self.assertIn("PlayResX: 1080\nPlayResY: 1920", portrait.read_text())
            self.assertIn("PlayResX: 1920\nPlayResY: 1080", landscape.read_text())


if __name__ == "__main__":
    unittest.main()
