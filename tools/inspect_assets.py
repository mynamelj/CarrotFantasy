"""Inspect LuaJIT chunks without executing game code."""

import argparse
import hashlib
import io
import json
import struct
import zipfile
from pathlib import Path

from asset_codec import decode
from bytecode_patch import read_uleb


def describe(data, instructions=False):
    stream = io.BytesIO(data)
    if stream.read(5) != b"\x1bLJ\x02\x08":
        raise ValueError("Unsupported LuaJIT header. Expected 1b 4c 4a 02 08.")
    name = stream.read(read_uleb(stream)).decode("utf-8", "replace")
    prototypes = []
    while length := read_uleb(stream):
        raw = stream.read(length)
        if len(raw) != length:
            raise ValueError("Truncated prototype.")
        proto = io.BytesIO(raw)
        flags, parameters, slots, upvalues = proto.read(4)
        gc_count, numbers, count, debug_size = (read_uleb(proto) for _ in range(4))
        firstline = read_uleb(proto) if debug_size else None
        line_span = read_uleb(proto) if debug_size else None
        code = proto.read(count * 4)
        row = {
            "index": len(prototypes), "firstline": firstline,
            "line_span": line_span, "parameters": parameters,
            "slots": slots, "upvalues": upvalues,
            "gc_constants": gc_count, "number_constants": numbers,
            "instructions": count, "flags": flags,
        }
        if instructions:
            row["code"] = [
                {
                    "pc": pc + 1, "hex": word.hex(),
                    "opcode": word[0], "a": word[1],
                    "b": word[3], "c": word[2],
                    "d": struct.unpack_from("<H", word, 2)[0],
                }
                for pc, word in enumerate(code[i:i + 4] for i in range(0, len(code), 4))
            ]
        prototypes.append(row)
    if stream.read():
        raise ValueError("Unexpected trailing bytecode bytes.")
    return {"source": name, "prototypes": prototypes}


def inspect(raw, path, instructions=False):
    data = decode(raw) if raw.startswith(b"\xff\xdb\xff\xee") else raw
    if not data.startswith(b"\x1bLJ"):
        return None
    row = describe(data, instructions)
    row.update(path=path, sha256=hashlib.sha256(raw).hexdigest())
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--contains", default="")
    parser.add_argument("--instructions", action="store_true")
    args = parser.parse_args()
    rows = []
    if args.input.suffix.lower() == ".apk":
        with zipfile.ZipFile(args.input) as archive:
            for name in archive.namelist():
                if name.startswith("assets/src/"):
                    row = inspect(archive.read(name), name, args.instructions)
                    if row and args.contains in row["source"]:
                        rows.append(row)
    else:
        paths = sorted(args.input.rglob("*")) if args.input.is_dir() else [args.input]
        for path in paths:
            if path.is_file():
                row = inspect(path.read_bytes(), str(path), args.instructions)
                if row and args.contains in row["source"]:
                    rows.append(row)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
