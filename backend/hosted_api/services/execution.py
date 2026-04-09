"""Execution-mode routing for the hosted product."""

from __future__ import annotations

from pathlib import Path

from ..config import get_settings


def resolve_execution_mode() -> str:
    """Return the configured execution mode."""
    return get_settings().execution_mode


def describe_execution_mode() -> dict:
    """Return a small status object for API and docs."""
    mode = resolve_execution_mode()
    return {
        "mode": mode,
        "supports_hpc": mode == "hpc",
        "message": (
            "Local execution mode routes jobs into the current backend engine."
            if mode == "local"
            else "HPC execution mode is reserved for future MedicineBow job submission."
        ),
    }


def ensure_hpc_placeholder(run_dir: Path) -> None:
    """Write a marker file for future HPC execution wiring."""
    run_dir.mkdir(parents=True, exist_ok=True)
    marker = run_dir / "HPC_MODE_NOT_YET_CONNECTED.txt"
    marker.write_text(
        "This hosted job was routed to HPC mode, but remote submission wiring has not "
        "been connected yet. Switch EFFECTOR_EXECUTION_MODE=local for now.\n",
        encoding="utf-8",
    )
