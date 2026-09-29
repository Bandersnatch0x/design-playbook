#!/usr/bin/env python3
"""Clean-install smoke for the design-playbook workbench (A15 support).

This is an operator/acceptance tool, not part of the shipped package.

It builds the wheel, installs that wheel into a **fresh** virtual
environment, starts the service as a subprocess from a **neutral working
directory** (proving the installed distribution does not need the
development checkout), and then drives the running service over real HTTP.

It covers exactly one A15 item: "clean install". It deliberately does NOT
cover, and never claims: Windows ACL / junction / file-occupation semantics,
performance p95, keyboard-only completion, or the two real-Agent journeys.
Those stay ``not-run``/``blocked`` in the acceptance ledger until they are
actually measured on the required host.

Usage::

    python tools/install_smoke.py                 # build, install, probe
    python tools/install_smoke.py --wheel dist/design_playbook_workbench-0.1.0-py3-none-any.whl
    python tools/install_smoke.py --evidence .benchmarks/install-smoke.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = TOOLS_DIR.parent
LAUNCH_TIMEOUT_SECONDS = 60
ENTRY_POINT = "design-playbook-workbench"

#: Files that must never appear in the shipped wheel.
_FORBIDDEN_PREFIXES = (".dbg", ".patch", ".insert", ".check_nest", ".depth", ".scratch")

#: The only wheel entry roots that may ship: the app package and its metadata.
_ALLOWED_ROOTS = ("design_playbook_workbench/",)


def unexpected_entries(names: list[str]) -> list[str]:
    """Wheel entries outside the app package and its dist-info.

    A whitelist, not a blocklist: the shipped distribution is the application
    package plus its metadata and nothing else, so new scratch, tooling or
    test trees cannot slip in unnoticed.
    """
    unexpected: list[str] = []
    for name in names:
        if name.startswith(_ALLOWED_ROOTS) or ".dist-info/" in name:
            continue
        unexpected.append(name)
    return unexpected


# -- deterministic helpers (unit-tested, no side effects) ----------------


def parse_launch(stdout_text: str) -> dict:
    """Parse the launch JSON ``launcher.describe`` prints.

    Accumulated stdout may include nothing else, but this tolerates leading
    noise by scanning for the first complete JSON object.
    """
    text = stdout_text.strip()
    if not text:
        raise ValueError("empty launch output")
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in launch output")
    decoder = json.JSONDecoder()
    payload, _ = decoder.raw_decode(text[start:])
    if not isinstance(payload, dict):
        raise ValueError("launch output is not a JSON object")
    for key in ("authority", "bootstrapUrl", "dataDir"):
        if key not in payload:
            raise ValueError(f"launch output missing {key!r}")
    return payload


def bootstrap_secret(launch: dict) -> str:
    """The one-time secret, taken from the fragment of the bootstrap URL."""
    url = launch["bootstrapUrl"]
    marker = "#bootstrap="
    if marker not in url:
        raise ValueError("bootstrap URL carries no secret fragment")
    return url.split(marker, 1)[1]


def venv_executable(venv_dir: Path, name: str) -> Path:
    """Path of a console script inside a venv, across platforms."""
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def forbidden_entries(names: list[str]) -> list[str]:
    """Wheel entries that would leak scratch files or test suites."""
    leaked: list[str] = []
    for name in names:
        base = name.rsplit("/", 1)[-1]
        if base.startswith(_FORBIDDEN_PREFIXES):
            leaked.append(name)
        elif "/tests/" in name or base.startswith("test_"):
            leaked.append(name)
    return leaked


def summarise(
    *, wheel: str, python: str, probes: dict, forbidden: list[str],
    unexpected: list[str],
) -> dict:
    """The evidence payload, with the A15 scope stated honestly."""
    return {
        "kind": "workbench-clean-install-smoke",
        "env": {
            "platform": platform.platform(),
            "python": python,
            "osName": os.name,
        },
        "wheel": wheel,
        "probes": probes,
        "wheelForbiddenEntries": forbidden,
        "wheelUnexpectedEntries": unexpected,
        "covers": ["A15 clean install: wheel installs and runs standalone"],
        "doesNotCover": [
            "Windows ACL / junction / file-occupation semantics",
            "performance p95 at R15 scale",
            "keyboard-only completion and viewport checks",
            "the two real-Agent journeys (A11/A12)",
        ],
    }


# -- live steps ----------------------------------------------------------


def _run(
    command: list[str], *, cwd: Path | None = None, timeout: int = 600
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def build_wheel(work: Path) -> Path:
    completed = _run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(work / "dist")],
        cwd=PACKAGE_DIR,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "wheel build failed:\n" + (completed.stdout + completed.stderr)[-2000:]
        )
    wheels = sorted((work / "dist").glob("*.whl"))
    if not wheels:
        raise SystemExit("no wheel produced")
    return wheels[-1]


def _request(
    url: str, *, method: str = "GET", body: dict | None = None,
    token: str | None = None, origin: str | None = None,
) -> tuple[int, str]:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if origin is not None:
        headers["Origin"] = origin
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def _await_launch(process: subprocess.Popen) -> tuple[dict, str]:
    """Read stdout until the launch JSON is complete, or time out."""
    deadline = time.monotonic() + LAUNCH_TIMEOUT_SECONDS
    buffer = ""
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if not line:
            if process.poll() is not None:
                raise SystemExit(
                    f"service exited early (code {process.returncode}): {buffer!r}"
                )
            continue
        buffer += line
        try:
            return parse_launch(buffer), buffer
        except ValueError:
            continue
    raise SystemExit(f"service did not print a launch line within timeout: {buffer!r}")


def run_smoke(wheel: Path, work: Path) -> dict:
    """Install into a fresh venv, start standalone, probe over HTTP."""
    venv_dir = work / "venv"
    created = _run([sys.executable, "-m", "venv", str(venv_dir)])
    if created.returncode != 0:
        raise SystemExit("venv creation failed:\n" + created.stderr[-2000:])

    python = venv_python(venv_dir)
    installed = _run(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check",
         "--no-input", str(wheel)]
    )
    if installed.returncode != 0:
        raise SystemExit("wheel install failed:\n" + installed.stderr[-2000:])

    entry = venv_executable(venv_dir, ENTRY_POINT)
    if not entry.exists():
        raise SystemExit(f"console script missing after install: {entry}")

    data_dir = work / "installed-data"
    neutral_cwd = work / "neutral-cwd"
    neutral_cwd.mkdir(parents=True, exist_ok=True)

    probes: dict[str, object] = {}
    process = subprocess.Popen(
        [str(entry), "--data-dir", str(data_dir), "--port", "0"],
        cwd=str(neutral_cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        launch, raw = _await_launch(process)
        probes["launchPrinted"] = True
        probes["launchKeys"] = sorted(launch)

        authority = str(launch["authority"])
        secret = bootstrap_secret(launch)

        status, body = _request(
            f"{authority}/api/v1/session",
            method="POST",
            body={"bootstrap": secret},
            origin=authority,
        )
        probes["sessionExchange"] = status
        if status != 200:
            raise SystemExit(f"bootstrap exchange failed: {status} {body[:400]}")
        token = json.loads(body)["token"]

        status, body = _request(f"{authority}/api/v1/projects", token=token)
        probes["projectsListing"] = status
        probes["projectsInitial"] = len(json.loads(body)["projects"]) if status == 200 else None

        status, body = _request(f"{authority}/")
        probes["staticShell"] = status
        probes["staticShellBytes"] = len(body)
        probes["staticShellLooksLikeApp"] = "<html" in body.lower()

        probes["dataDirCreated"] = data_dir.is_dir()
        probes["ranFromNeutralCwd"] = True
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            process.kill()
            process.wait(timeout=20)

    version = _run([str(python), "-c", "import platform;print(platform.python_version())"])
    wheel_names = zipfile.ZipFile(wheel).namelist()
    evidence = summarise(
        wheel=str(wheel),
        python=version.stdout.strip() or "unknown",
        probes=probes,
        forbidden=forbidden_entries(wheel_names),
        unexpected=unexpected_entries(wheel_names),
    )
    evidence["launchRawLineCount"] = raw.count("\n")
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="install_smoke.py",
        description="Install the built wheel in a fresh venv and probe it (A15).",
    )
    parser.add_argument("--wheel", default=None, help="Use this wheel instead of building.")
    parser.add_argument("--work", default=None, help="Scratch dir (default: temp).")
    parser.add_argument("--evidence", default=None, help="Write JSON evidence here.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    work = Path(args.work).resolve() if args.work else Path(tempfile.mkdtemp())
    work.mkdir(parents=True, exist_ok=True)
    wheel = (
        Path(args.wheel).expanduser().resolve()
        if args.wheel
        else build_wheel(work)
    )
    if not wheel.is_file():
        print(f"wheel not found: {wheel}", file=sys.stderr)
        return 2

    evidence = run_smoke(wheel, work)
    leaked = evidence["wheelForbiddenEntries"]
    unexpected = evidence["wheelUnexpectedEntries"]
    if leaked or unexpected:
        # A non-app wheel entry is a hard failure of this smoke, not a note.
        print(
            f"wheel carries entries outside the app package: "
            f"forbidden={leaked} unexpected={unexpected}",
            file=sys.stderr,
        )
        return 3

    text = json.dumps(evidence, indent=2, ensure_ascii=False)
    print(text)
    if args.evidence:
        out = Path(args.evidence)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"\nevidence: {out}")
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry
    raise SystemExit(main())
