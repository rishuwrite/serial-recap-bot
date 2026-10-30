import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recap"))

import render
import social


class FacebookVerticalTests(unittest.TestCase):
    def test_facebook_always_enables_vertical_rendering(self):
        with mock.patch.dict(os.environ, {
            "FACEBOOK_ENABLED": "true",
            "FACEBOOK_PAGE_ID": "page",
            "FACEBOOK_PAGE_ACCESS_TOKEN": "token",
            "FACEBOOK_REELS_MODE": "false",
            "RENDER_VERTICAL": "false",
        }, clear=True):
            self.assertTrue(social.should_render_vertical())

    def test_landscape_video_is_rejected_before_upload(self):
        probe = SimpleNamespace(
            stdout=json.dumps({"streams": [{"width": 1920, "height": 1080}]}),
        )
        with mock.patch.object(social.subprocess, "run", return_value=probe):
            with self.assertRaisesRegex(ValueError, "must be 9:16"):
                social._validate_vertical_video("landscape.mp4")

    def test_vertical_video_is_accepted(self):
        probe = SimpleNamespace(
            stdout=json.dumps({"streams": [{"width": 1080, "height": 1920}]}),
        )
        with mock.patch.object(social.subprocess, "run", return_value=probe):
            social._validate_vertical_video("vertical.mp4")

    def test_landscape_thumbnail_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            thumb = Path(folder) / "landscape.jpg"
            Image.new("RGB", (1280, 720)).save(thumb)
            with self.assertRaisesRegex(ValueError, "thumbnails must be 9:16"):
                social._validate_vertical_thumbnail(str(thumb))

    def test_facebook_upload_attaches_custom_cover(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "vertical.mp4"
            thumb = Path(folder) / "vertical.jpg"
            video.write_bytes(b"mp4")
            Image.new("RGB", (1080, 1920)).save(thumb)
            responses = [
                mock.Mock(status_code=200, json=lambda: {
                    "upload_session_id": "session",
                    "video_id": "video",
                    "start_offset": 0,
                    "end_offset": 3,
                }),
                mock.Mock(status_code=200, json=lambda: {
                    "start_offset": 3,
                    "end_offset": 3,
                }),
                mock.Mock(status_code=200, json=lambda: {}),
            ]
            with mock.patch.dict(os.environ, {
                "FACEBOOK_ENABLED": "true",
                "FACEBOOK_PAGE_ID": "page",
                "FACEBOOK_PAGE_ACCESS_TOKEN": "token",
            }, clear=True), \
                    mock.patch.object(social, "_validate_vertical_video") as validate, \
                    mock.patch.object(social.requests, "post", side_effect=responses) as post:
                video_id = social.upload_facebook_video(
                    str(video), "Episode", "Caption", thumb_path=str(thumb)
                )

        self.assertEqual(video_id, "video")
        validate.assert_called_once_with(str(video))
        finish_files = post.call_args.kwargs["files"]
        self.assertEqual(finish_files["thumb"][0], "thumb.jpg")

    def test_facebook_cover_is_rendered_in_vertical_format(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "art.jpg"
            output = Path(folder) / "cover.jpg"
            Image.new("RGB", (1280, 720), (90, 30, 20)).save(source)
            with mock.patch.object(render, "deva", side_effect=lambda text: text), \
                    mock.patch.object(render, "font", return_value=ImageFont.load_default()):
                render.thumbnail_vertical(
                    str(source), "Maha twist", "Show name", "Episode 12", str(output)
                )

            with Image.open(output) as cover:
                self.assertEqual(cover.size, (1080, 1920))


if __name__ == "__main__":
    unittest.main()
