"""Rebuild a patch bundle from clean, locally captured game scripts."""

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from asset_codec import decode, encode
from bytecode_patch import patch_chunk
from inject_source import hook_chunk
from stabilize_money import stabilize_money


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value):
    if not re.fullmatch(r"[0-9a-f]{32}/src/(?:[0-9]+/)+[0-9]+", value):
        raise ValueError(f"Unexpected cache path: {value}")
    return Path(*PurePosixPath(value).parts)


def build(profile_path, input_root, output_root, coop_owned_range=False,
          no_donation_cooldown=False, append_sunflower=False):
    if not __debug__:
        raise ValueError("Run Python without -O so bytecode assertions stay enabled.")
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    version = profile["version"]
    if not re.fullmatch(r"\d+(?:\.\d+)+", version):
        raise ValueError("Invalid game version.")
    if append_sunflower and not any(record["kind"] == "build_selection" for record in profile["files"]):
        raise ValueError("The profile has no build selection targets.")
    # Validate and transform all files before writing any output.
    transformed = []
    for record in profile["files"]:
        kind = record["kind"]
        if kind == "build_selection" and not append_sunflower:
            continue
        relative = safe_path(record["path"])
        raw = (input_root / relative).read_bytes()
        if digest(raw) != record["original"]:
            raise ValueError(f"Clean input hash mismatch: {relative}")
        decoded = decode(raw)
        if kind == "build_selection":
            patched = hook_chunk(decoded, Path(__file__).with_name("append_solo_towers.lua").read_bytes())
        elif kind in ("money", "range"):
            patched = patch_chunk(decoded, record["firstline"],
                                  coop_owned_range=coop_owned_range and kind == "range",
                                  no_donation_cooldown=no_donation_cooldown and kind == "money")
            if kind == "money":
                patched = stabilize_money(patched)
        else:
            raise ValueError(f"Unknown patch kind: {kind}")
        encoded = bytes(encode(raw, patched))
        if decode(encoded) != patched:
            raise ValueError(f"Asset codec roundtrip failed: {relative}")
        item = {
            "path": record["path"],
            "original": record["original"],
            "patched": digest(encoded),
            "previous": record.get("previous", []),
        }
        transformed.append((relative, encoded, item))

    archive = output_root.with_name(output_root.name + ".zip")
    if archive.exists():
        raise ValueError(f"Archive already exists: {archive}")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("Choose a new or empty output directory.")
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": version,
        "apk": profile["apk"],
        "files": [item for _, _, item in transformed],
    }
    if coop_owned_range:
        manifest["coop_owned_range"] = True
    if no_donation_cooldown:
        manifest["no_donation_cooldown"] = True
    if append_sunflower:
        manifest["append_sunflower"] = True
    for relative, encoded, _ in transformed:
        target = output_root / "payload" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copyfile(
        Path(__file__).with_name("Apply-CarrotPatch.ps1"),
        output_root / "Apply-CarrotPatch.ps1",
    )
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(output_root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output_root).as_posix())
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--coop-owned-range", action="store_true",
                        help="Enable full-map range for the local player's co-op towers.")
    parser.add_argument("--no-donation-cooldown", action="store_true",
                        help="Skip the local cooldown after confirming a co-op donation.")
    parser.add_argument("--append-solo-towers", "--append-sunflower", dest="append_sunflower",
                        action="store_true",
                        help="Append Sun and Crystal to the build selection in solo modes.")
    args = parser.parse_args()
    print(build(args.profile, args.input, args.output, args.coop_owned_range,
                args.no_donation_cooldown, args.append_sunflower))


if __name__ == "__main__":
    main()
