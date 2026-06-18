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

    # Initialise BLAST/TM-align globals — these are set by validate_binaries()
    # which the HTTP server calls at startup but is skipped on plain import.
    try:
        engine.validate_binaries()
    except Exception:
        pass  # degraded mode — individual callers check availability flags

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
    """Call upload_sequence + classify, bypassing the background-task wrapper."""
    import uuid
    from datetime import datetime

    async def runner():
        seq_result = await engine.upload_sequence(
            request.sequence or "",
            request.sequence_id,
        )
        job_id = request.sequence_id or f"seq_{uuid.uuid4().hex[:8]}"
        query_id = seq_result.query_id or job_id
        classification = engine._classify_sequence_result(seq_result, query_id)
        alphafold_queued = seq_result.status in ["novel_sequence", "structure_missing"]
        processing_result = engine.ProcessingResult(
            job_id=job_id,
            status="completed",
            results=[classification],
            completed_at=datetime.now().isoformat(),
            alphafold_queued=alphafold_queued,
        )
        return processing_result.model_dump()

    return asyncio.run(runner())


def _run_structure_or_fasta_job(engine, request_payload: dict[str, Any]) -> dict[str, Any]:
    import uuid
    from datetime import datetime

    staged_path = Path(request_payload["staged_path"])
    original_filename = request_payload["original_filename"]
    input_type = request_payload["input_type"]
    upload_file = _make_upload_file(staged_path, original_filename)

    async def runner():
        job_id = f"{input_type}_{uuid.uuid4().hex[:8]}"
        query_id = original_filename

        if input_type == "structure":
            match_result = await engine.upload_structure(upload_file)
            classification = engine._classify_structure_result(
                match_result, query_id.rsplit(".", 1)[0]
            )
            processing_result = engine.ProcessingResult(
                job_id=job_id,
                status="completed",
                results=[classification],
                completed_at=datetime.now().isoformat(),
                alphafold_queued=False,
            )
        else:
            # FASTA — convert MultiSequenceResult to ProcessingResult
            multi_result = await engine.upload_multisequence(upload_file)
            classification_results = []
            alphafold_queued = False
            for i, seq_result in enumerate(multi_result.results):
                qid = seq_result.query_id or f"seq_{i+1}"
                classification_results.append(engine._classify_sequence_result(seq_result, qid))
                if seq_result.status in ["novel_sequence", "structure_missing"]:
                    alphafold_queued = True
            processing_result = engine.ProcessingResult(
                job_id=job_id,
                status="completed",
                results=classification_results,
                completed_at=datetime.now().isoformat(),
                alphafold_queued=alphafold_queued,
            )

        return processing_result.model_dump()

    return asyncio.run(runner())


def run_real_pipeline(request_payload: dict[str, Any], result_path: Path) -> dict:
    """Run the current backend pipeline through the hosted scaffold."""
    engine = _load_engine_module()
    request = JobCreateRequest.model_validate(request_payload)
    job_id = request_payload.get("job_id") or result_path.stem

    if request.input_type == "sequence":
        processing_result = _run_sequence_job(engine, request)
    else:
        processing_result = _run_structure_or_fasta_job(engine, request_payload)

    # ChimeraX headless rendering — generate a PNG of the best-match structure
    structure_image_path: str | None = None
    try:
        from ..config import get_settings as _get_settings  # noqa: WPS433
        from .chimerax_renderer import render_structure_png  # noqa: WPS433

        first_result = (processing_result.get("results") or [{}])[0]
        best_match_id = first_result.get("best_match_id")
        if best_match_id:
            pdb_path_str = engine._get_pdb_path_from_structure_name(best_match_id)
            if pdb_path_str:
                pdb_path = Path(pdb_path_str)
                output_png = result_path.parent / "structure_preview.png"
                settings = _get_settings()
                if render_structure_png(pdb_path, output_png, settings.chimerax_bin):
                    structure_image_path = str(output_png)
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("ChimeraX step failed: %s", _exc)

    alphafold_result: dict[str, Any] | None = None
    if request.input_type == "sequence" and request.run_alphafold:
        from .alphafold_runner import run_alphafold_prediction  # noqa: WPS433

        alphafold_output_dir = result_path.parent / "alphafold" / str(job_id)
        sequence_id = request.sequence_id or job_id
        alphafold_result = run_alphafold_prediction(
            sequence_id=sequence_id,
            sequence=request.sequence or "",
            output_dir=alphafold_output_dir,
        )

    result = {
        "processing_result": processing_result,
        "summary": _build_summary(processing_result),
    }
    if alphafold_result is not None:
        result["alphafold"] = alphafold_result
    if structure_image_path is not None:
        result["structure_image_path"] = structure_image_path
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
