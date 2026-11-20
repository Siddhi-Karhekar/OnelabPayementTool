"""Zip the project into onelab_submission.zip for submission.

Run from the project root: python make_zip.py
Excludes git data, caches, virtual environments, git bundles and the zip itself.
"""
import fnmatch
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ZIP_NAME = "onelab_submission.zip"
EXCLUDED_DIRS = {".git", ".claude", "__pycache__", ".pytest_cache", ".venv", "venv"}
EXCLUDED_FILES = ["*.bundle", ZIP_NAME, "*.pyc"]


def included(path: Path) -> bool:
    """True if the file should go into the zip."""
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return False
    return not any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_FILES)


def make_zip() -> list[str]:
    """Write the zip and return the archived paths."""
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and included(p))
    names = []
    with zipfile.ZipFile(ROOT / ZIP_NAME, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            name = path.relative_to(ROOT).as_posix()
            zf.write(path, name)
            names.append(name)
    return names


if __name__ == "__main__":
    archived = make_zip()
    print(f"Wrote {ZIP_NAME} with {len(archived)} files:")
    for name in archived:
        print(f"  {name}")
