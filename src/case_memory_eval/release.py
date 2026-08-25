"""One-command local release verification."""

import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path


def _run(*command: str) -> None:
    subprocess.run(command, check=True)


def _verify_packages(dist: Path) -> None:
    wheels = sorted(dist.glob("*.whl"))
    source_archives = sorted(dist.glob("*.tar.gz"))
    if not wheels or not source_archives:
        raise RuntimeError("release build did not produce wheel and source archives")
    required = {
        "case_memory_eval/api.py",
        "case_memory_eval/cli.py",
        "case_memory_eval/ui.py",
        "case_memory_eval/py.typed",
    }
    with zipfile.ZipFile(wheels[-1]) as archive:
        wheel_files = set(archive.namelist())
    if not required <= wheel_files:
        raise RuntimeError(f"wheel is missing package files: {sorted(required - wheel_files)}")
    with tarfile.open(source_archives[-1]) as archive:
        source_files = {name.split("/", 1)[-1] for name in archive.getnames()}
    if "fixtures/cases.json" not in source_files:
        raise RuntimeError("source archive is missing the golden corpus")


def main() -> None:
    """Run static checks, tests, demo, build, and package-content inspection."""
    with tempfile.TemporaryDirectory(prefix="case-memory-release-") as temporary:
        demo_path = str(Path(temporary) / "demo")
        dist_path = Path(temporary) / "dist"
        _run("uv", "run", "--no-sync", "ruff", "format", "--check", ".")
        _run("uv", "run", "--no-sync", "ruff", "check", ".")
        _run("uv", "run", "--no-sync", "mypy")
        _run("uv", "run", "--no-sync", "pytest", "--cov", "--cov-report=term-missing")
        _run("uv", "run", "--no-sync", "case-memory-eval", "demo", "--output", demo_path)
        _run("uv", "build", "--out-dir", str(dist_path))
        _verify_packages(dist_path)
    print("Release checks passed: static analysis, tests, demo, build, and package contents.")


if __name__ == "__main__":
    main()
