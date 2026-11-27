from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "aliyun_fun_asr.py"
SPEC = importlib.util.spec_from_file_location("aliyun_fun_asr", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AliyunFunAsrTests(unittest.TestCase):
    def test_payload_keeps_complete_context(self) -> None:
        context = "护肤旁白" * 200
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "voice.mp3"
            audio.write_bytes(b"test-audio")
            payload = MODULE.build_payload(
                audio, "audio/mpeg", MODULE.DEFAULT_MODEL, context
            )

        actual = payload["input"]["messages"][1]["content"][0]["text"]

        self.assertEqual(actual, context)

    def test_normalizes_word_timestamps(self) -> None:
        response = {
            "output": {
                "text": "大家好，我是小医。",
                "sentence": {
                    "text": "大家好，我是小医。",
                    "words": [
                        {"text": "大家好", "begin_time": 13760, "end_time": 14080},
                        {"text": "我是小医", "begin_time": 14080, "end_time": 14720},
                    ],
                },
            },
            "request_id": "request-test",
        }

        normalized = MODULE.normalize_response(response, 15.0, MODULE.DEFAULT_MODEL)

        self.assertEqual(normalized["segments"][0]["words"][0]["start"], 13.76)
        self.assertEqual(normalized["metadata"]["timestamp_source"], "aliyun_fun_asr_flash")
        self.assertEqual(normalized["metadata"]["request_id"], "request-test")

    def test_rejects_non_monotonic_timestamps(self) -> None:
        response = {
            "output": {
                "sentence": {
                    "words": [
                        {"text": "大家", "begin_time": 100, "end_time": 300},
                        {"text": "好", "begin_time": 200, "end_time": 400},
                    ]
                }
            }
        }

        with self.assertRaisesRegex(MODULE.AsrError, "不单调"):
            MODULE.normalize_response(response, 1.0, MODULE.DEFAULT_MODEL)


if __name__ == "__main__":
    unittest.main()
