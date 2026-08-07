"""WB-436 resumable object storage, dedupe, grants and cleanup contracts."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import asset_object_store  # noqa: E402
import db  # noqa: E402
from config import settings  # noqa: E402
from routers import assets, business  # noqa: E402


class AssetObjectStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self.old_root = settings.OBJECT_STORAGE_DIR
        self.old_part = settings.ASSET_UPLOAD_PART_BYTES
        self._close()
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        settings.OBJECT_STORAGE_DIR = Path(self.temp.name) / "objects"
        settings.ASSET_UPLOAD_PART_BYTES = 4
        db.init_db()
        self.owner = db.create_account(name="owner-436", password="password123")
        self.other = db.create_account(name="other-436", password="password123")
        self.project = db.create_project(name="Asset project", owner_id=self.owner.id)
        self.owner_token = db.create_token(self.owner.id)[0]
        self.other_token = db.create_token(self.other.id)[0]
        app = FastAPI()
        app.include_router(assets.router)
        app.include_router(business.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self._close()
        settings.DB_PATH = self.old_db
        settings.OBJECT_STORAGE_DIR = self.old_root
        settings.ASSET_UPLOAD_PART_BYTES = self.old_part
        db._local = threading.local()
        self.temp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def _headers(self, other: bool = False) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.other_token if other else self.owner_token}"}

    def _asset(self, data: bytes, key: str) -> str:
        response = self.client.post(
            "/api/assets",
            headers={**self._headers(), "Idempotency-Key": key},
            json={
                "project_id": self.project.id, "name": f"{key}.bin", "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["asset"]["id"]

    def test_resume_complete_download_dedupe_and_revocation(self) -> None:
        data = b"same-object"
        sha256 = hashlib.sha256(data).hexdigest()
        asset_id = self._asset(data, "asset-one")
        started = self.client.post(
            "/api/assets/uploads", headers=self._headers(),
            json={"asset_id": asset_id, "size": len(data), "sha256": sha256},
        )
        self.assertEqual(200, started.status_code, started.text)
        upload = started.json()["upload"]
        upload_id = upload["id"]
        first = data[:4]
        response = self.client.put(
            f"/api/assets/uploads/{upload_id}/parts/0", headers={
                **self._headers(), "X-Part-SHA256": hashlib.sha256(first).hexdigest(),
            }, content=first,
        )
        self.assertEqual(200, response.status_code, response.text)

        resumed = self.client.post(
            "/api/assets/uploads", headers=self._headers(),
            json={"asset_id": asset_id, "size": len(data), "sha256": sha256},
        ).json()["upload"]
        self.assertEqual(upload_id, resumed["id"])
        self.assertTrue(resumed["resumed"])
        status = self.client.get(f"/api/assets/uploads/{upload_id}", headers=self._headers()).json()["upload"]
        self.assertEqual([0], [part["part_number"] for part in status["parts"]])
        for number, part in enumerate((data[4:8], data[8:]), start=1):
            response = self.client.put(
                f"/api/assets/uploads/{upload_id}/parts/{number}", headers={
                    **self._headers(), "X-Part-SHA256": hashlib.sha256(part).hexdigest(),
                }, content=part,
            )
            self.assertEqual(200, response.status_code, response.text)
        completed = self.client.post(
            f"/api/assets/uploads/{upload_id}/complete", headers=self._headers(),
        )
        self.assertEqual(200, completed.status_code, completed.text)
        version_id = completed.json()["object_version"]["id"]

        self.assertEqual(
            404,
            self.client.post(f"/api/assets/{asset_id}/download-grant", headers=self._headers(True)).status_code,
        )
        grant = self.client.post(
            f"/api/assets/{asset_id}/download-grant", headers=self._headers(),
        ).json()
        downloaded = self.client.get(
            f"/api/assets/{asset_id}/content", headers={"X-Asset-Token": grant["token"]},
        )
        self.assertEqual(data, downloaded.content)
        self.assertEqual(sha256, downloaded.headers["X-Asset-SHA256"])
        self.assertEqual(version_id, downloaded.headers["X-Asset-Version"])

        second_id = self._asset(data, "asset-two")
        deduped = self.client.post(
            "/api/assets/uploads", headers=self._headers(),
            json={"asset_id": second_id, "size": len(data), "sha256": sha256},
        ).json()["upload"]
        self.assertEqual("committed", deduped["state"])
        self.assertTrue(deduped["deduplicated"])
        self.assertEqual(1, len(list((settings.OBJECT_STORAGE_DIR / "objects").rglob(sha256))))

        asset = self.client.get(f"/api/assets/{asset_id}", headers=self._headers()).json()
        deleted = self.client.delete(
            f"/api/assets/{asset_id}", params={"expected_version": asset["version"]},
            headers=self._headers(),
        )
        self.assertEqual(200, deleted.status_code, deleted.text)
        self.assertEqual(
            401,
            self.client.get(
                f"/api/assets/{asset_id}/content", headers={"X-Asset-Token": grant["token"]},
            ).status_code,
        )
        self.assertTrue(asset_object_store.object_path(f"objects/{sha256[:2]}/{sha256}").is_file())

    def test_hash_mismatch_and_expired_multipart_cleanup(self) -> None:
        data = b"abcdefgh"
        asset_id = self._asset(data, "bad-part")
        upload = self.client.post(
            "/api/assets/uploads", headers=self._headers(),
            json={"asset_id": asset_id, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()},
        ).json()["upload"]
        rejected = self.client.put(
            f"/api/assets/uploads/{upload['id']}/parts/0",
            headers={**self._headers(), "X-Part-SHA256": "0" * 64}, content=data[:4],
        )
        self.assertEqual(409, rejected.status_code, rejected.text)
        part = data[:4]
        accepted = self.client.put(
            f"/api/assets/uploads/{upload['id']}/parts/0",
            headers={**self._headers(), "X-Part-SHA256": hashlib.sha256(part).hexdigest()}, content=part,
        )
        self.assertEqual(200, accepted.status_code, accepted.text)
        db.get_conn().execute(
            "UPDATE asset_uploads SET expires_at=? WHERE id=?", (time.time() - 1, upload["id"]),
        )
        db.get_conn().commit()
        result = asset_object_store.cleanup_expired()
        self.assertEqual(1, result["uploads"])
        self.assertFalse((settings.OBJECT_STORAGE_DIR / "uploads" / upload["id"]).exists())
        self.assertEqual(
            "expired",
            db.get_conn().execute("SELECT state FROM asset_uploads WHERE id=?", (upload["id"],)).fetchone()[0],
        )

    def test_large_multipart_and_forged_commit_are_rejected(self) -> None:
        settings.ASSET_UPLOAD_PART_BYTES = 4 * 1024 * 1024
        data = b"L" * (8 * 1024 * 1024 + 123)
        sha256 = hashlib.sha256(data).hexdigest()
        asset_id = self._asset(data, "large-object")
        forged = self.client.patch(
            f"/api/assets/{asset_id}", headers=self._headers(),
            json={"expected_version": 1, "storage_state": "committed", "object_ref": "file:///tmp/fake"},
        )
        self.assertEqual(400, forged.status_code, forged.text)
        started = self.client.post(
            "/api/assets/uploads", headers=self._headers(),
            json={"asset_id": asset_id, "size": len(data), "sha256": sha256},
        )
        self.assertEqual(200, started.status_code, started.text)
        upload = started.json()["upload"]
        self.assertEqual(4 * 1024 * 1024, upload["part_size"])
        for number, offset in enumerate(range(0, len(data), upload["part_size"])):
            part = data[offset:offset + upload["part_size"]]
            response = self.client.put(
                f"/api/assets/uploads/{upload['id']}/parts/{number}",
                headers={**self._headers(), "X-Part-SHA256": hashlib.sha256(part).hexdigest()},
                content=part,
            )
            self.assertEqual(200, response.status_code, response.text)
        completed = self.client.post(
            f"/api/assets/uploads/{upload['id']}/complete", headers=self._headers(),
        )
        self.assertEqual(200, completed.status_code, completed.text)
        self.assertEqual(sha256, completed.json()["object_version"]["sha256"])


if __name__ == "__main__":
    unittest.main()
