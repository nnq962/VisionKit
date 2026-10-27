"""Kiểm chuẩn hoá URL YouTube độc lập mạng và dependency tải video."""

import unittest

from app.core.youtube import normalize_youtube_url


# ------------------------- Kiểm liên kết video đơn ----------------------------
class YoutubeUrlTests(unittest.TestCase):
    """Chấp nhận các dạng link video; từ chối playlist, host giả và URL tuỳ ý."""

    def test_canonical_video_links_strip_tracking(self) -> None:
        """Các dạng URL đều trỏ cùng video và bỏ query theo dõi/playlist."""
        for url in [
            "https://youtu.be/BaW_jenozKc?si=private",
            "https://www.youtube.com/watch?v=BaW_jenozKc&list=PLtest",
            "http://m.youtube.com/shorts/BaW_jenozKc",
            "https://youtube.com/live/BaW_jenozKc",
            "https://www.youtube.com/embed/BaW_jenozKc",
        ]:
            self.assertEqual(
                normalize_youtube_url(url),
                "https://www.youtube.com/watch?v=BaW_jenozKc",
            )

    def test_invalid_urls_never_echo_input(self) -> None:
        """Host giả, login, ID sai và ký tự điều khiển không lọt resolver."""
        for url in [
            "https://youtube.com.evil.test/watch?v=BaW_jenozKc",
            "https://youtube.com/playlist?list=private",
            "file:///private",
            "https://private@youtube.com/watch?v=BaW_jenozKc",
            "https://youtube.com:443/watch?v=BaW_jenozKc",
            "https://youtube.com/watch?v=private",
            "https://youtu.be/BaW_jenozKc/extra",
            "https://youtube.com/watch?v=BaW_jenozKc&v=private",
            "https://you\ntube.com/watch?v=BaW_jenozKc",
        ]:
            with self.assertRaises(ValueError) as error:
                normalize_youtube_url(url)
            self.assertNotIn("private", str(error.exception))
