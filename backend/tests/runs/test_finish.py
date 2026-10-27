"""Kiểm hoàn thành lượt chạy thu hồi đúng tài nguyên tạm và bảo toàn thư viện."""

import unittest

from tests.runs import test_api as fixtures


# ------------------------ Kiểm vòng đời hoàn thành lượt -----------------------
class FinishRunTests(unittest.TestCase):
    """Dùng DB/storage thật, AI giả để kiểm file, JSON và model lease sau cleanup."""

    setUp = fixtures.RunTests.setUp
    make_client = fixtures.RunTests.make_client
    handle = fixtures.RunTests.handle
    start = fixtures.RunTests.start
    wait = fixtures.RunTests.wait

    def test_completed_snapshot_cleanup_is_idempotent_and_preserves_library(
        self,
    ) -> None:
        """Hoàn thành xoá snapshot/run, giữ file nguồn/model đã lưu; gọi lại vẫn 204."""
        source = self.client.post(
            "/api/v1/sources/upload", files={"file": ("saved.png", self.image)}
        ).json()
        response = self.client.post(
            "/api/v1/runs",
            data={
                "source_id": source["id"],
                "model_id": self.model_id,
                "options": "{}",
            },
        )
        self.assertEqual(response.status_code, 202, response.text)
        record = self.wait(response.json()["id"])
        path = self.app.state.runs.storage.path(record["source_location"])
        self.assertTrue(path.is_file())
        for _ in range(2):
            self.assertEqual(
                self.client.delete(
                    f"/api/v1/runs/{record['id']}/resources"
                ).status_code,
                204,
            )
        self.assertFalse(path.exists())
        self.assertEqual(
            self.client.get(f"/api/v1/runs/{record['id']}").status_code, 404
        )
        self.assertEqual(
            self.client.get(f"/api/v1/sources/{source['id']}/content").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/api/v1/models/{self.model_id}").status_code, 200
        )
        self.assertFalse(self.app.state.runs.tasks)
        self.assertNotIn(self.model_id, self.app.state.models.in_use)

    def test_active_job_cleanup_waits_for_cancel_and_removes_ram_frame(self) -> None:
        """API cleanup cũng huỷ job active an toàn và bỏ frame cache của riêng run."""
        self.delay = 0.4
        response = self.start()
        run_id = response.json()["id"]
        self.app.state.runs.webcam_frames[run_id] = b"test-frame"
        self.assertEqual(
            self.client.delete(f"/api/v1/runs/{run_id}/resources").status_code, 204
        )
        self.assertIsNone(self.app.state.runs.repository.get(run_id))
        self.assertNotIn(run_id, self.app.state.runs.webcam_frames)
        self.assertFalse(self.app.state.runs.tasks)
        self.assertNotIn(self.model_id, self.app.state.models.in_use)
        self.assertEqual(list(self.app.state.runs.storage.root.iterdir()), [])
