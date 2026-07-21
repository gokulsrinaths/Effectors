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

    # ── Email + PDF report ──────────────────────────────────────────────────

    def test_email_is_validated_and_optional(self) -> None:
        app, SessionLocal, HostedJob, _ = self.load_app()
        with TestClient(app) as client:
            bad = client.post("/jobs", json={"input_type": "sequence", "sequence": "MKTAYIAK",
                                             "email": "not-an-email"})
            self.assertEqual(bad.status_code, 400)

            good = client.post("/jobs", json={"input_type": "sequence", "sequence": "MKTAYIAK",
                                              "email": "me@uwyo.edu"})
            self.assertEqual(good.status_code, 200)

            # Blank must still run the job — email is explicitly optional.
            blank = client.post("/jobs", json={"input_type": "sequence", "sequence": "MKTAYIAK"})
            self.assertEqual(blank.status_code, 200)

        with SessionLocal() as db:
            self.assertEqual(db.get(HostedJob, good.json()["id"]).email, "me@uwyo.edu")
            # None, not "", so `if not job.email` short-circuits cleanly.
            self.assertIsNone(db.get(HostedJob, blank.json()["id"]).email)

    def test_report_pdf_route_generates_lazily(self) -> None:
        import json as _json

        app, SessionLocal, HostedJob, _ = self.load_app()
        from backend.hosted_api.config import get_settings

        with TestClient(app) as client:
            created = client.post("/jobs", json={"input_type": "sequence", "sequence": "MKTAYIAK"})
            job_id = created.json()["id"]
            token = created.json()["access_token"]

            # No result yet.
            self.assertEqual(
                client.get(f"/jobs/files/{job_id}/report-pdf",
                           headers={"x-job-token": token}).status_code,
                404,
            )

            settings = get_settings()
            settings.results_dir.mkdir(parents=True, exist_ok=True)
            result_path = settings.results_dir / f"{job_id}.json"
            result_path.write_text(_json.dumps({
                "processing_result": {"results": [{
                    "query_id": "Q", "classification": "Known structural family",
                    "tm_score": 0.8, "best_match_id": "X",
                    "tm_align_result": {"tm_score": 0.8, "tm_score_chain1": 0.8,
                                        "tm_score_chain2": 0.77, "tm_score_best": 0.8,
                                        "alignment_type": "full_fold", "rmsd": 1.2,
                                        "alignment_length": 120, "top_matches": []},
                }]},
                "summary": {"message": "done"},
            }), encoding="utf-8")
            with SessionLocal() as db:
                job = db.get(HostedJob, job_id)
                job.result_path = str(result_path)
                job.status = "completed"
                db.commit()

            ok = client.get(f"/jobs/files/{job_id}/report-pdf", headers={"x-job-token": token})
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.headers["content-type"], "application/pdf")
            self.assertTrue(ok.content.startswith(b"%PDF-"))

            self.assertEqual(client.get(f"/jobs/files/{job_id}/report-pdf").status_code, 401)
            self.assertEqual(
                client.get(f"/jobs/files/{job_id}/report-pdf",
                           headers={"x-job-token": "wrong"}).status_code,
                403,
            )

    def test_email_failure_never_fails_a_completed_job(self) -> None:
        """A completed job must survive SMTP and PDF errors.

        Both call sites sit inside a broad `except Exception` that would otherwise
        re-queue a finished job over a mail timeout.
        """
        from unittest import mock

        self.load_app()
        from backend.hosted_api.services import job_runner
        from backend.hosted_api.models import HostedJob as Job

        job = Job(id="email-fail", input_type="sequence", email="me@uwyo.edu",
                  access_token_hash="x", status="completed", input_path="x",
                  backend_mode="local", attempt_count=1, max_attempts=2)

        with mock.patch.object(job_runner, "send_or_preview_email",
                               side_effect=RuntimeError("smtp timeout")):
            job_runner._send_completion_email(job, "msg", {})  # must not raise
        self.assertEqual(job.status, "completed")

        # A PDF failure must degrade to a text-only email, not suppress it.
        with mock.patch.object(job_runner, "build_job_report_pdf",
                               side_effect=RuntimeError("reportlab boom")):
            with mock.patch.object(job_runner, "send_or_preview_email") as sender:
                job_runner._send_completion_email(job, "msg", {})
                self.assertTrue(sender.called)
                self.assertIsNone(sender.call_args.kwargs["attachments"])

    def test_preview_files_do_not_collide_across_jobs(self) -> None:
        """Previews used to key on recipient alone, so each one clobbered the last."""
        self.load_app()
        from backend.hosted_api.services.emailer import write_email_preview

        preview_dir = Path(self.temp_dir.name) / "previews"
        for job_id in ("job-aaa", "job-bbb"):
            write_email_preview("me@uwyo.edu", f"Job {job_id}", "body",
                                preview_dir, preview_slug=job_id)

        self.assertEqual(len(list(preview_dir.glob("*.txt"))), 2)

    def test_report_pdf_survives_degraded_results(self) -> None:
        """Sparse or malformed results must still yield a PDF, never an exception."""
        self.load_app()
        from backend.hosted_api.services.report_pdf import build_job_report_pdf

        cases = {
            "empty": {},
            "no_matches": {"processing_result": {"results": [
                {"query_id": "Q", "classification": "Novel structure",
                 "tm_align_result": {"tm_score": 0.1, "tm_score_chain1": 0.1, "top_matches": []}}]}},
            "no_chain2": {"processing_result": {"results": [
                {"query_id": "Q", "classification": "Known structural family",
                 "tm_align_result": {"tm_score": 0.8, "tm_score_chain1": 0.8}}]}},
            "malformed": {"processing_result": {"results": [{"query_id": "Q"}]}},
        }
        for name, payload in cases.items():
            with self.subTest(case=name):
                path = build_job_report_pdf(f"degraded_{name}", payload)
                self.assertIsNotNone(path, f"{name} produced no PDF")
                self.assertTrue(path.read_bytes().startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
