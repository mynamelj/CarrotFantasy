"""List a chunk's constants and raw instructions using jit.util, without executing it."""

import argparse
import json
from pathlib import Path

from asset_codec import decode


def main():
    from lupa.luajit21 import LuaRuntime

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--line", type=int)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    data = decode(raw) if raw.startswith(b"\xff\xdb\xff\xee") else raw
    runtime = LuaRuntime(encoding=None)
    util = runtime.eval(b'require("jit.util")')
    kind = runtime.eval(b"type")
    root = runtime.eval(b"function(s) return assert(loadstring(s)) end")(data)
    rows = []

    def visit(function):
        info = util.funcinfo(function)
        constants = [util.funck(function, -i - 1) for i in range(info[b"gcconsts"])]
        if args.line is None or info[b"linedefined"] == args.line:
            values = []
            for index, value in enumerate(constants):
                if isinstance(value, bytes):
                    text = value.decode("utf-8", "replace")
                elif kind(value) == b"proto":
                    text = f"child at line {util.funcinfo(value)[b'linedefined']}"
                else:
                    text = f"<{kind(value).decode()}>"
                values.append({"index": index, "value": text})
            code = []
            for pc in range(1, info[b"bytecodes"]):
                word, _ = util.funcbc(function, pc)
                word &= 0xFFFFFFFF
                code.append({
                    "pc": pc, "opcode": f"0x{word & 255:02x}",
                    "hex": word.to_bytes(4, "little").hex(),
                    "a": (word >> 8) & 255, "b": word >> 24,
                    "c": (word >> 16) & 255, "d": word >> 16,
                })
            rows.append({
                "firstline": info[b"linedefined"], "lastline": info[b"lastlinedefined"],
                "parameters": info[b"params"], "gc_constants": values,
                "code": code,
            })
        for value in constants:
            if kind(value) == b"proto":
                visit(value)

    visit(root)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
