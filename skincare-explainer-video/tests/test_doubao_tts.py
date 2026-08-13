from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "doubao_tts.py"
SPEC = importlib.util.spec_from_file_location("doubao_tts", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DoubaoTtsTests(unittest.TestCase):
    def test_narration_sha256_uses_exact_trimmed_tts_text(self) -> None:
        text = "  第一句。\n\n第二句！  "

        result = MODULE.narration_sha256(text)

        self.assertEqual(
            result,
            hashlib.sha256("第一句。\n\n第二句！".encode("utf-8")).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
