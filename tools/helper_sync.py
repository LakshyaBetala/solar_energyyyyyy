"""Copies the Chrome helper from this folder to the folder the installed desktop app keeps it in, which is the
folder Chrome loaded it from. Run when Solara runs from source (run_web.bat does it), so that after the reload
arrow on chrome://extensions the helper in Chrome is the one in this folder.

The copy's manifest gets a version_name with the time of the copy. Chrome shows it on chrome://extensions, so it
is plain which helper is loaded.

  python tools/helper_sync.py
"""
import json, os, shutil, sys, time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "extension"
DST = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Solara" / "resources" / "backend" / "_internal" / "extension"


def main():
    if not DST.is_dir():
        print(f"  The desktop app's helper folder was not found:\n    {DST}\n  In Chrome, load the helper from this folder instead:\n    {SRC}")
        return 0
    for f in SRC.iterdir():   # shortcut: the helper is a flat folder of files; copy sub-folders too if it ever gets one
        if f.is_file():
            shutil.copy2(f, DST / f.name)
    m = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
    m["version_name"] = f'{m["version"]} ({time.strftime("%d %b %H:%M")})'
    (DST / "manifest.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    same = all((DST / f.name).read_bytes() == f.read_bytes() for f in SRC.iterdir() if f.is_file() and f.name != "manifest.json")
    assert same, "the copy does not match this folder"
    print(f'  Helper {m["version_name"]} is in the desktop app\'s folder.\n  In Chrome: chrome://extensions, the reload arrow on the Solara helper, then reload the portal tab.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
