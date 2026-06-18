"""Release-safety tests for the hosted API contract."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import gc
import os
from pathlib import Path
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def purge_hosted_modules() -> None:
    for module_name in list(sys.modules):
        if module_name.startswith("backend.hosted_api"):
            del sys.modules[module_name]


class HostedApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls) -> None:
        # Dispose all SQLAlchemy engines so Windows releases SQLite file locks
        for mod_name, mod in list(sys.modules.items()):
            if mod_name.startswith("backend.hosted_api") and hasattr(mod, "engine"):
                try:
                    mod.engine.dispose()
                except Exception:
                    pass
        gc.collect()
        cls.temp_dir.cleanup()

    def load_app(self, *, rate_limit: int = 30):
        db_path = Path(self.temp_dir.name) / f"{self._testMethodName}.db"
        os.environ["EFFECTOR_HOSTED_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        os.environ["EFFECTOR_ADMIN_API_KEY"] = "test-admin-key"
        os.environ["EFFECTOR_EXECUTION_MODE"] = "local"
        os.environ["EFFECTOR_RATE_LIMIT_CREATE_JOB_LIMIT"] = str(rate_limit)
        os.environ["EFFECTOR_RATE_LIMIT_WINDOW_SECONDS"] = "60"
        os.environ["EFFECTOR_CORS_ALLOWED_ORIGINS"] = "http://localhost:3000"
        purge_hosted_modules()

        from backend.hosted_api.main import app
        from backend.hosted_api.db import SessionLocal
        from backend.hosted_api.models import HostedJob
        from backend.hosted_api.worker import reserve_next_job

        return app, SessionLocal, HostedJob, reserve_next_job

    def test_job_creation_requires_token_for_access(self) -> None:
        app, _, _, _ = self.load_app()
        with TestClient(app) as client:
            create_response = client.post(
                "/jobs",
                json={
                    "input_type": "sequence",
                    "sequence": "MKTAYIAKQRQISFVKSHFSRQ",
                    "sequence_id": "EFF_001",
                },
            )
            self.assertEqual(create_response.status_code, 200)
            payload = create_response.json()
            self.assertIn("access_token", payload)
            self.assertNotIn("input_path", payload)
            self.assertFalse(payload["has_result"])

            denied_response = client.get(payload["poll_path"])
            self.assertEqual(denied_response.status_code, 401)

            allowed_response = client.get(
                payload["poll_path"],
                headers={"x-job-token": payload["access_token"]},
            )
            self.assertEqual(allowed_response.status_code, 200)
            self.assertEqual(allowed_response.json()["id"], payload["id"])

    def test_admin_list_requires_api_key(self) -> None:
        app, _, _, _ = self.load_app()
        with TestClient(app) as client:
            response = client.get("/jobs")
            self.assertEqual(response.status_code, 401)

            authorized = client.get("/jobs", headers={"x-api-key": "test-admin-key"})
            self.assertEqual(authorized.status_code, 200)

    def test_create_job_rate_limit_applies(self) -> None:
        app, _, _, _ = self.load_app(rate_limit=2)
        with TestClient(app) as client:
            for sequence_id in ("EFF_001", "EFF_002"):
                response = client.post(
                    "/jobs",
                    json={
                        "input_type": "sequence",
                        "sequence": "MKTAYIAKQRQISFVKSHFSRQ",
                        "sequence_id": sequence_id,
                    },
                )
                self.assertEqual(response.status_code, 200)

            limited = client.post(
                "/jobs",
                json={
                    "input_type": "sequence",
                    "sequence": "MKTAYIAKQRQISFVKSHFSRQ",
                    "sequence_id": "EFF_003",
                },
            )
            self.assertEqual(limited.status_code, 429)

    def test_upload_extension_validation(self) -> None:
        app, _, _, _ = self.load_app()
        with TestClient(app) as client:
            response = client.post(
                "/jobs/upload",
                data={"input_type": "structure"},
                files={"file": ("bad.txt", b"not-a-pdb", "text/plain")},
            )
            self.assertEqual(response.status_code, 400)

    def test_reserve_next_job_reclaims_stale_running_job(self) -> None:
        app, SessionLocal, HostedJob, reserve_next_job = self.load_app()
        with TestClient(app):
            pass

        with SessionLocal() as db:
            db.add(
                HostedJob(
                    id="stale-job",
                    input_type="sequence",
                    email=None,
                    access_token_hash="hash",
                    status="running",
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10),
                    started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10),
                    reservation_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5),
                    input_path=str(Path(self.temp_dir.name) / "stale.request.json"),
                    backend_mode="local",
                    attempt_count=1,
                    max_attempts=2,
                )
            )
            db.commit()

        reclaimed = reserve_next_job("worker-test")
        self.assertIsNotNone(reclaimed)
        self.assertEqual(reclaimed.id, "stale-job")
        self.assertEqual(reclaimed.status, "reserved")


if __name__ == "__main__":
    unittest.main()
