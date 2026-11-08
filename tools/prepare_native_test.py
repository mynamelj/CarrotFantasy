"""Prepare temporary VM probes and their restore files under an ignored directory."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath

from asset_codec import decode, encode
from inject_source import hook_chunk
from build_patch import safe_path


BOOTSTRAP = rb'''
local cls = ...
local ctor = cls.ctor
cls.ctor = function(self, ...)
    local result = ctor(self, ...)
    local ok, err = pcall(require, "gamescene.GameLayer")
    if not ok then
        local f = io.open("/data/user/0/com.feiyu.luobo4/files/.carrot_coin_selftest.log", "a")
        if f then f:write("require-error ", tostring(err), "\n"); f:close() end
    end
    return result
end
'''


def main():
    from lupa.luajit21 import LuaRuntime

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("Choose a new or empty probe directory.")
    profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
    manifest = json.loads((args.bundle / "manifest.json").read_text(encoding="utf-8-sig"))
    hasher = hashlib.sha256()
    with args.apk.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            hasher.update(block)
    if hasher.hexdigest() != manifest["apk"]:
        raise ValueError("The local original APK hash differs from the bundle.")
    source = Path(__file__).with_name("native_coin_selftest.lua").read_bytes()
    runtime = LuaRuntime(encoding=None)
    compile_source = runtime.eval(b"function(s) return assert(loadstring(s)) ~= nil end")
    assert compile_source(source) and compile_source(BOOTSTRAP)
    extra_paths = []
    restore_paths = []

    def write(relative, raw, directory):
        target = args.output / directory / safe_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    for item in profile["files"]:
        if item["kind"] != "money":
            continue
        relative = item["path"]
        raw = (args.bundle / "payload" / safe_path(relative)).read_bytes()
        expected = next(entry["patched"] for entry in manifest["files"] if entry["path"] == relative)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"Bundle hash mismatch: {relative}")
        write(relative, raw, "restore")
        write(relative, bytes(encode(raw, hook_chunk(decode(raw), source))), "probe")
        restore_paths.append(relative)
    anchor = PurePosixPath(profile["files"][0]["path"]).parts[0]
    with zipfile.ZipFile(args.apk) as apk:
        for name in profile["bootstrap_assets"]:
            if not name.startswith("assets/src/"):
                raise ValueError("Unexpected bootstrap asset path.")
            relative = anchor + "/" + name.removeprefix("assets/")
            raw = apk.read(name)
            write(relative, bytes(encode(raw, hook_chunk(decode(raw), BOOTSTRAP))), "probe")
            extra_paths.append(relative)
    (args.output / "probe-manifest.json").write_text(json.dumps({
        "version": profile["version"], "restore_paths": restore_paths,
        "extra_paths": extra_paths,
    }, indent=2) + "\n", encoding="utf-8")
    print(args.output / "probe-manifest.json")


if __name__ == "__main__":
    main()
