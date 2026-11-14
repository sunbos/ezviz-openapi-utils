"""Private child entry point: block Python network I/O before importing the SDK."""

from __future__ import annotations

import io
import json
import socket
import sys
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


class _DiscardOutput(io.TextIOBase):
    def __init__(self) -> None:
        self.used = False

    def write(self, text: str) -> int:
        if text:
            self.used = True
        return len(text)

    def flush(self) -> None:
        pass


def main() -> int:
    inputs = json.load(sys.stdin)
    root = Path(inputs["repo_root"]).resolve()
    # The evaluator is trusted tooling; only the SDK source comes from --repo.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    output = _DiscardOutput()
    network_attempted = False

    def denied(*args, **kwargs):
        nonlocal network_attempted
        network_attempted = True
        raise RuntimeError("evaluation network access blocked")

    report = None
    with ExitStack() as stack:
        for target, name in (
            (socket.socket, "connect"),
            (socket.socket, "connect_ex"),
            (socket.socket, "sendto"),
            (socket, "create_connection"),
            (socket, "getaddrinfo"),
        ):
            stack.enter_context(patch.object(target, name, denied))
        if hasattr(socket.socket, "sendmsg"):
            stack.enter_context(patch.object(socket.socket, "sendmsg", denied))
        stack.enter_context(redirect_stdout(output))
        stack.enter_context(redirect_stderr(output))
        try:
            from harness.wire_eval import evaluate

            sys.path.insert(0, str(root / "src"))
            report = evaluate(inputs["contracts"], inputs["bindings"], inputs["cases"], root)
        except Exception:
            # Never echo candidate exceptions, stdout, request values or response values.
            report = None
    if report is None:
        return 2
    if network_attempted or output.used:
        report["passed"] = False
        report["coverage_complete"] = False
        report["guard_failure"] = (
            "network_attempt" if network_attempted else "unexpected_sdk_output"
        )
    sys.stdout.write(json.dumps(report, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
