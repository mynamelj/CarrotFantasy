"""Capture target scripts from a rooted emulator into an ignored local directory."""

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

from inspect_assets import inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--use-backups", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"\d+(?:\.\d+)+", args.version):
        raise ValueError("Invalid version.")

    def adb(*command):
        return subprocess.check_output([args.adb, "-s", args.serial, *command])

    if adb("shell", "id -u").strip() != b"0":
        raise ValueError("Run adb root on the intended emulator first.")
    package = "com.feiyu.luobo4"
    installed = adb("shell", f"pm path {package}").decode().strip()
    if not re.fullmatch(r"package:/data/app/[^\s']+/base\.apk", installed):
        raise ValueError("Unexpected installed APK path.")
    apk_hash = adb("shell", f"sha256sum '{installed[8:]}'").decode().split()[0]
    app_files = f"/data/user/0/{package}/files"
    cache = f"{app_files}/hotupdate/{args.version}"
    archive = adb("exec-out", f"cd '{cache}' && tar -cf - */src")
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("Choose a new or empty capture directory.")
    records = []
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            if not member.isfile():
                continue
            if not re.fullmatch(r"[0-9a-f]{32}/src/(?:[0-9]+/)+[0-9]+", member.name):
                continue
            raw = tar.extractfile(member).read()
            row = inspect(raw, member.name)
            if not row:
                continue
            source = row["source"].replace("\\", "/")
            if "/src/gamescene/GameLayer.lua" in source:
                kind, parameters, count = "money", 5, 164
            elif "/src/tower/Tower.lua" in source:
                kind, parameters, count = "range", 1, 68
            else:
                continue
            if args.use_backups:
                saved = f"{app_files}/.carrot-original-{args.version}/{member.name}"
                raw = adb("exec-out", f"cat '{saved}'")
                row = inspect(raw, member.name)
            candidates = [
                p for p in row["prototypes"]
                if p["parameters"] == parameters and p["instructions"] == count
                and p["firstline"] is not None
            ]
            firstline = candidates[0]["firstline"] if len(candidates) == 1 else None
            target = args.output / Path(*PurePosixPath(member.name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            records.append({
                "path": member.name, "kind": kind, "firstline": firstline,
                "original": hashlib.sha256(raw).hexdigest(), "previous": [],
                "source": row["source"],
            })
    if not records:
        raise ValueError("No supported target scripts found. Inspect the current update layout.")
    candidate = {
        "version": args.version, "package": package, "apk": apk_hash,
        "files": sorted(records, key=lambda item: item["path"]),
    }
    profile = args.output / "candidate-profile.json"
    profile.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(records)} targets. Review {profile} before building.")


if __name__ == "__main__":
    main()
