"""Builds dist/modelerkit-<version>.zip and refreshes dist/index.json, the repository Blender 4.5 checks for
updates. The team adds https://raw.githubusercontent.com/msrk0320/ModelerKit/master/dist/index.json once (see the
README). Older zips move to dist/old so the index lists only the newest. Run: python build.py"""
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe")
DIST = HERE / "dist"

version = re.search(r'^version = "(.+)"', (HERE / "modelerkit" / "blender_manifest.toml").read_text(), re.M).group(1)
zip_path = DIST / f"modelerkit-{version}.zip"

(DIST / "old").mkdir(parents=True, exist_ok=True)
for old in DIST.glob("modelerkit-*.zip"):
    if old != zip_path:
        shutil.move(old, DIST / "old" / old.name)
zip_path.unlink(missing_ok=True)
subprocess.run([str(BLENDER), "--command", "extension", "build", "--source-dir", str(HERE / "modelerkit"),
                "--output-dir", str(DIST)], check=True, stdout=subprocess.DEVNULL)
if not zip_path.exists():
    raise SystemExit(f"Build failed: {zip_path.name} not written")
subprocess.run([str(BLENDER), "--command", "extension", "server-generate", "--repo-dir", str(DIST)],
               check=True, stdout=subprocess.DEVNULL)
print(f"Built {zip_path.name}; in Blender: Get Extensions > Check for Updates (or restart), then Update on Modeler Kit")
