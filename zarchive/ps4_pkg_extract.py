"""Non-destructive PS4 PKG extraction orchestration.

The publisher tools are supplied by the user; no binaries or passcodes are bundled.
A retail package may require keys that these tools cannot access.
"""
from __future__ import annotations

import re
from pathlib import Path

PASSCODE = re.compile(r"^[0-9a-fA-F]{32}$")
PKG_LIMIT = 250 * 1024 * 1024 * 1024

def validate_executable(path, expected):
    candidate = Path(path).expanduser()
    if candidate.is_symlink() or not candidate.is_file() or candidate.name.casefold() != expected.casefold():
        raise ValueError(f"Select the installed {expected} executable.")
    if candidate.stat().st_size < 2:
        raise ValueError("Executable is empty.")
    with candidate.open("rb") as handle:
        if handle.read(2) != b"MZ":
            raise ValueError("Selected file is not a Windows executable.")
    return candidate.resolve(strict=True)

def validate_input(pkg, output, executable, passcode):
    source = Path(pkg).expanduser()
    if source.is_symlink() or not source.is_file() or source.suffix.casefold() != ".pkg":
        raise ValueError("Select an existing, regular .pkg file.")
    if not 0 < source.stat().st_size <= PKG_LIMIT:
        raise ValueError("PKG is empty or exceeds the 250 GiB safety limit.")
    source = source.resolve(strict=True)
    dest = Path(output).expanduser()
    if dest.is_symlink():
        raise ValueError("Output directory cannot be a symlink.")
    if not dest.is_dir():
        raise ValueError("Choose an existing output parent folder.")
    dest = dest.resolve(strict=True)
    if dest == source.parent:
        raise ValueError("Choose an output parent separate from the PKG source folder.")
    exe = validate_executable(executable, "orbis-pub-cmd.exe")
    if passcode and not PASSCODE.fullmatch(passcode):
        raise ValueError("Passcode must be exactly 32 hexadecimal characters.")
    return source, dest, exe

def prepare_extract(pkg, output_parent, executable, passcode):
    """Return safe QProcess args; user-selected output is never overwritten.

    Final output directory isn't created until execution, to avoid leaving empty folders
    on validation failures. The GUI creates its private work directory before starting.
    """
    source, parent, exe = validate_input(pkg, output_parent, executable, passcode)
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", source.stem).strip("._")[:80] or "package"
    target = parent / (name + "_extracted")
    if target.exists() or target.is_symlink():
        raise FileExistsError("Output already exists. Move or rename it before extracting.")
    # Do not pass a fabricated passcode if none was provided.
    args = ["img_extract"]
    if passcode:
        args.extend(["--passcode", passcode])
    args.extend([str(source), str(target)])
    return {"program": str(exe), "args": args, "target": str(target),
            "source": str(source), "passcode": passcode}

def redact(text, passcode):
    if passcode:
        return text.replace(passcode, "[REDACTED]")
    return text
