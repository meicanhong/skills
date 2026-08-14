#!/usr/bin/env python3

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import seedance


class SeedanceTests(unittest.TestCase):
    def base_args(self, **overrides):
        values = {
            "prompt": "一只猫打哈欠",
            "first_frame": None,
            "last_frame": None,
            "reference_image": [],
            "reference_video": [],
            "reference_audio": [],
            "resolution": "720p",
            "ratio": "16:9",
            "duration": 5,
            "seed": None,
            "watermark": False,
            "generate_audio": None,
            "return_last_frame": None,
            "output_format": None,
            "callback_url": None,
            "execution_expires_after": None,
            "priority": None,
            "service_tier": None,
            "safety_identifier": None,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_text_payload_omits_unspecified_options(self):
        payload = seedance.build_payload(self.base_args(), seedance.DEFAULT_MODEL)
        self.assertEqual(payload["model"], seedance.DEFAULT_MODEL)
        self.assertEqual(payload["content"], [{"type": "text", "text": "一只猫打哈欠"}])
        self.assertEqual(payload["watermark"], False)
        self.assertNotIn("seed", payload)

    def test_model_text_is_required_even_with_reference_media(self):
        args = self.base_args(prompt="   ", reference_image=["https://example.com/a.png"])
        with self.assertRaisesRegex(seedance.SeedanceError, "模型 text"):
            seedance.build_content(args)

    def test_camera_fixed_is_never_added_to_mini_payload(self):
        payload = seedance.build_payload(
            self.base_args(camera_fixed=True),
            seedance.DEFAULT_MODEL,
        )
        self.assertNotIn("camera_fixed", payload)

    def test_accepts_duration_boundaries(self):
        for duration in (4, 15):
            with self.subTest(duration=duration):
                payload = seedance.build_payload(
                    self.base_args(duration=duration), seedance.DEFAULT_MODEL
                )
                self.assertEqual(payload["duration"], duration)

    def test_rejects_duration_outside_mini_range(self):
        for duration in (3, 16):
            with self.subTest(duration=duration):
                with self.assertRaisesRegex(seedance.SeedanceError, "4–15 秒整数"):
                    seedance.build_payload(
                        self.base_args(duration=duration), seedance.DEFAULT_MODEL
                    )

    def test_old_approval_with_camera_fixed_is_rejected_before_api(self):
        payload = seedance.build_payload(self.base_args(), seedance.DEFAULT_MODEL)
        payload["camera_fixed"] = True
        with self.assertRaisesRegex(seedance.SeedanceError, "不支持的 camera_fixed"):
            seedance.validate_payload_model_compatibility(payload)

    def test_old_approval_with_three_second_duration_is_rejected_before_api(self):
        payload = seedance.build_payload(self.base_args(), seedance.DEFAULT_MODEL)
        payload["duration"] = 3
        with self.assertRaisesRegex(seedance.SeedanceError, "4–15 秒整数"):
            seedance.validate_payload_model_compatibility(payload)

    def test_frame_and_reference_are_mutually_exclusive(self):
        args = self.base_args(first_frame="https://example.com/a.png", reference_image=["https://example.com/b.png"])
        with self.assertRaisesRegex(seedance.SeedanceError, "互斥"):
            seedance.build_content(args)

    def test_last_frame_requires_first_frame(self):
        with self.assertRaisesRegex(seedance.SeedanceError, "first-frame"):
            seedance.build_content(self.base_args(last_frame="https://example.com/end.png"))

    def test_local_image_becomes_data_url(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "a.png"
            image.write_bytes(b"png-test")
            result = seedance.media_url(str(image), "image")
        self.assertTrue(result.startswith("data:image/png;base64,"))

    def test_local_video_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "a.mp4"
            video.write_bytes(b"video-test")
            with self.assertRaisesRegex(seedance.SeedanceError, "公网 URL"):
                seedance.media_url(str(video), "video")

    def test_task_id_validation(self):
        self.assertEqual(seedance.validate_task_id("cgt-abc_123"), "cgt-abc_123")
        with self.assertRaises(seedance.SeedanceError):
            seedance.validate_task_id("../../secret")

    def test_supported_models_and_default(self):
        catalog = seedance.model_catalog()
        self.assertEqual(catalog["default_model"], "doubao-seedance-2-0-mini-260615")
        self.assertEqual(len(catalog["models"]), 1)
        self.assertEqual(catalog["models"][0]["model_id"], seedance.DEFAULT_MODEL)
        self.assertEqual(sum(model["default"] for model in catalog["models"]), 1)

    def test_rejects_every_non_mini_model(self):
        for model in (
            "doubao-seedance-2-5-260628",
            "doubao-seedance-2-0-260128",
            "doubao-seedance-2-0-fast-260128",
            "doubao-seedance-1-5-pro-251215",
        ):
            with self.subTest(model=model):
                with self.assertRaisesRegex(seedance.SeedanceError, "仅允许模型"):
                    seedance.validate_model(model)

    def test_accepts_only_mini_model(self):
        self.assertEqual(seedance.validate_model(seedance.DEFAULT_MODEL), seedance.DEFAULT_MODEL)

    def test_rejects_non_mini_model_from_environment(self):
        with mock.patch.dict("os.environ", {"SEEDANCE_MODEL": "doubao-seedance-2-0-fast-260128"}):
            with self.assertRaisesRegex(seedance.SeedanceError, "仅允许模型"):
                seedance.resolve_model(None)

    def test_approval_requires_prepare_approve_consume_sequence(self):
        payload = seedance.build_payload(self.base_args(), seedance.DEFAULT_MODEL)
        summary = seedance.generation_summary(self.base_args(), seedance.DEFAULT_MODEL)
        with tempfile.TemporaryDirectory() as directory:
            store = seedance.ApprovalStore(Path(directory))
            prepared = store.prepare(payload, summary)
            approval_id = prepared["approval_id"]
            self.assertEqual(prepared["request"]["model_text"], "一只猫打哈欠")
            self.assertIn("确认", prepared["confirmation_prompt"])
            with self.assertRaisesRegex(seedance.SeedanceError, "未确认"):
                store.consume(approval_id)
            approved = store.approve(approval_id)
            self.assertEqual(approved["status"], "approved")
            consumed = store.consume(approval_id)
            self.assertEqual(consumed["payload"], payload)
            with self.assertRaisesRegex(seedance.SeedanceError, "已使用"):
                store.consume(approval_id)

    def test_approval_id_rejects_path_traversal(self):
        with self.assertRaises(seedance.SeedanceError):
            seedance.validate_approval_id("../../invalid")


if __name__ == "__main__":
    unittest.main()
