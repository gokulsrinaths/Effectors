"""Remote HPC entrypoint for executing one hosted job inside the repo clone."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one hosted effector job on a remote worker node.")
    parser.add_argument("--request", required=True, help="Path to the staged request JSON file.")
    parser.add_argument("--result", required=True, help="Path where the result JSON should be written.")
    args = parser.parse_args()

    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from hosted_api.services.pipeline_adapter import run_real_pipeline  # noqa: WPS433

    request_path = Path(args.request)
    result_path = Path(args.result)
    request_payload = json.loads(request_path.read_text(encoding="utf-8"))
    run_real_pipeline(request_payload, result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
