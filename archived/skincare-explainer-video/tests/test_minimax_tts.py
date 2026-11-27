from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "minimax_tts.py"
SPEC = importlib.util.spec_from_file_location("minimax_tts", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
TEST_VOICE_ID = "AuthorizedVoice01"


class MiniMaxTtsTests(unittest.TestCase):
    def test_default_voice_is_company_authorized_laowang_voice(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch.object(
            MODULE, "MINIMAX_ENV", Path("/tmp/nonexistent-skincare-video-bundle.env")
        ):
            self.assertEqual(
                MODULE.resolve_voice_id(),
                "GuangxiLaoWang_Studio_20260814",
            )

    def test_narration_sha256_uses_exact_trimmed_tts_text(self) -> None:
        text = "  第一句。\n\n第二句！  "

        result = MODULE.narration_sha256(text)

        self.assertEqual(
            result,
            hashlib.sha256("第一句。\n\n第二句！".encode("utf-8")).hexdigest(),
        )

    def test_command_uses_expected_default_production_parameters(self) -> None:
        args = argparse.Namespace(
            timeout=120.0,
            voice_id=TEST_VOICE_ID,
            output=Path("/tmp/narration.mp3"),
            language_boost="Chinese",
            speed=1.0,
            sample_rate=44100,
            bitrate=128000,
            emotion=None,
        )

        command = MODULE.build_minimax_command(args, "测试旁白", Path("/tmp/provider.json"))

        self.assertIn("speech-2.8-hd", MODULE.MODEL)
        self.assertEqual(command[command.index("--voice-id") + 1], TEST_VOICE_ID)
        self.assertEqual(command[command.index("--language-boost") + 1], "Chinese")
        self.assertNotIn("--emotion", command)

    def test_command_adds_emotion_only_when_explicit(self) -> None:
        args = argparse.Namespace(
            timeout=120.0,
            voice_id=TEST_VOICE_ID,
            output=Path("/tmp/narration.mp3"),
            language_boost="Chinese",
            speed=1.0,
            sample_rate=44100,
            bitrate=128000,
            emotion="calm",
        )

        command = MODULE.build_minimax_command(args, "测试旁白", Path("/tmp/provider.json"))

        self.assertEqual(command[command.index("--emotion") + 1], "calm")


if __name__ == "__main__":
    unittest.main()
