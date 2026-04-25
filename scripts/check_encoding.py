from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable


DEFAULT_EXTENSIONS = {
    ".py",
    ".js",
    ".json",
    ".md",
    ".txt",
    ".css",
    ".html",
    ".yml",
    ".yaml",
    ".toml",
}

DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".vscode",
    "huggingface",
    "reference_novels",
    "text_style_imitation",
    "novel_projects",
    "Screenshots",
    "codex_tmp",
    ".codex-temp",
    "pytest-cache-files-3021pw2l",
    "pytest-cache-files-4j18mil3",
    "pytest_basetemp_run",
}

DEFAULT_EXCLUDE_FILES = {
    "scripts/check_encoding.py",
}

# Typical mojibake fragments produced when UTF-8 Chinese text is decoded with a
# Western code page and then saved back into source files.
SUSPICIOUS_FRAGMENTS = (
    "å",
    "æ",
    "ç",
    "é",
    "è",
    "ä",
    "ö",
    "ü",
    "ß",
    "鍘",
    "鍚",
    "鏀",
)


def iter_target_files(root: Path, extensions: set[str]) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in DEFAULT_EXCLUDE_DIRS for part in path.parts):
            continue
        relative_path = path.relative_to(root).as_posix()
        if relative_path in DEFAULT_EXCLUDE_FILES:
            continue
        if path.suffix.lower() in extensions:
            yield path


def find_suspicious_lines(path: Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [(0, "File is not valid UTF-8")]

    findings: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if any(fragment in line for fragment in SUSPICIOUS_FRAGMENTS):
            findings.append((lineno, line.strip()))
    return findings


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")

    parser = argparse.ArgumentParser(
        description="Scan source files for suspicious mojibake fragments."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Files or directories to scan. Defaults to the current directory.",
    )
    args = parser.parse_args()

    extensions = DEFAULT_EXTENSIONS
    findings_found = False

    for raw_path in args.paths:
        path = Path(raw_path).resolve()
        if not path.exists():
            print(f"[WARN] Path does not exist: {raw_path}")
            continue

        targets = [path] if path.is_file() else list(iter_target_files(path, extensions))
        for target in targets:
            findings = find_suspicious_lines(target)
            if not findings:
                continue
            findings_found = True
            for lineno, snippet in findings:
                line_label = "?" if lineno == 0 else str(lineno)
                print(f"[ENCODING] {target}:{line_label}: {snippet}")

    if findings_found:
        print(
            "\nEncoding check failed. These lines look like mojibake or non-UTF-8 content."
        )
        return 1

    print("Encoding check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
