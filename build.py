"""Builds dist\modelerkit-<version>.zip. Run: python build.py"""
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe")

(HERE / "dist").mkdir(exist_ok=True)
subprocess.run([str(BLENDER), "--command", "extension", "build", "--source-dir", str(HERE / "modelerkit"),
                "--output-dir", str(HERE / "dist")], check=True)
