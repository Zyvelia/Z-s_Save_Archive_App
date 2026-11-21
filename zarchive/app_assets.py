"""Resolve app resources from source and PyInstaller one-folder builds."""
from pathlib import Path
import sys

def asset_path(filename: str) -> Path:
    allowed = {"ZSaveArchive.png", "ZSaveArchive.ico", "ZSaveArchive_Original.png", "Retail2Pkg_ISO_Launcher_v3.zip"}
    if filename not in allowed:
        raise ValueError("Unknown application asset")
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / filename
    return Path(__file__).resolve().parent.parent / "assets" / filename
