"""Execution-mode routing for the hosted product."""

from __future__ import annotations

from ..config import get_settings


def resolve_execution_mode() -> str:
    """Return the configured execution mode."""
    return get_settings().execution_mode


def describe_execution_mode() -> dict:
    """Return a small status object for API and docs."""
    mode = resolve_execution_mode()
    settings = get_settings()
    return {
        "mode": mode,
        "supports_hpc": mode == "hpc",
        "message": (
            "Local execution mode routes jobs into the current backend engine."
            if mode == "local"
            else (
                "HPC execution mode submits remote Slurm jobs over SSH. "
                f"Remote host alias: {settings.hpc_remote_host_alias}."
            )
        ),
    }
