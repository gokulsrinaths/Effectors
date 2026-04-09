"""Adapter seam between the hosted job system and the current research pipeline."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from fastapi import UploadFile

from ..schemas import JobCreateRequest


def _load_engine_module():
    """Load the current backend engine from backend/main.py."""
    backend_root = Path(__file__).resolve().parents[2]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    import main as engine  # type: ignore

    return engine


def _build_summary(processing_result: dict[str, Any]) -> dict[str, Any]:
    """Create a condensed summary for result pages and email."""
    results = processing_result.get("results", [])
    first = results[0] if results else {}
    blast_result = first.get("blast_result") or {}
    return {
        "classification": first.get("classification", "no-result"),
        "best_match_id": first.get("best_match_id"),
        "tm_score": first.get("tm_score"),
        "blast_hit_id": blast_result.get("hit_id"),
        "message": (
            f"Job completed with {len(results)} result item(s). "
            f"Primary classification: {first.get('classification', 'unknown')}."
        ),
        "result_count": len(results),
        "alphafold_queued": processing_result.get("alphafold_queued", False),
    }


def _make_upload_file(path: Path, filename: str) -> UploadFile:
    """Create an UploadFile from a staged file path."""
    temp = tempfile.SpooledTemporaryFile()
    temp.write(path.read_bytes())
    temp.seek(0)
    return UploadFile(file=temp, filename=filename)


def _run_sequence_job(engine, request: JobCreateRequest) -> dict[str, Any]:
    async def runner():
        req = engine.SequenceRequest(
            sequence=request.sequence or "",
            sequence_id=request.sequence_id,
        )
        result = await engine.api_process_sequence(req)
        return result.model_dump()

    return asyncio.run(runner())


def _run_structure_or_fasta_job(engine, request_payload: dict[str, Any]) -> dict[str, Any]:
    staged_path = Path(request_payload["staged_path"])
    original_filename = request_payload["original_filename"]
    upload_file = _make_upload_file(staged_path, original_filename)

    async def runner():
        if request_payload["input_type"] == "structure":
            result = await engine.api_process_structure(upload_file)
        else:
            result = await engine.api_process_fasta(upload_file)
        return result.model_dump()

    return asyncio.run(runner())


def run_real_pipeline(request_payload: dict[str, Any], result_path: Path) -> dict:
    """Run the current backend pipeline through the hosted scaffold."""
    engine = _load_engine_module()
    request = JobCreateRequest.model_validate(request_payload)

    if request.input_type == "sequence":
        processing_result = _run_sequence_job(engine, request)
    else:
        processing_result = _run_structure_or_fasta_job(engine, request_payload)

    result = {
        "processing_result": processing_result,
        "summary": _build_summary(processing_result),
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
