"""Verify bundle hashes, mode behavior and the per-function JIT guard."""

import argparse
import hashlib
import io
import json
from pathlib import Path

from asset_codec import decode
from bytecode_patch import (
    ENABLED_GAME_MODES, SINGLE_PLAYER_MODES, ad, read_uleb, uleb,
)


# These are this game's dump opcodes. Translate only the injected instructions
# into the stock LuaJIT 2.1 opcodes used by the host verification runtime.
OPCODES = {
    0x01: 1,       # ISGE
    0x04: 4,       # ISEQV
    0x0C: 39,      # KSTR
    0x0E: 41,      # KSHORT
    0x10: 43,      # KPRI
    0x2C: 34,      # MULVV
    0x3A: 54,      # GGET
    0x3C: 56,      # TGETV
    0x3D: 57,      # TGETS
    0x46: 66,      # CALL
    0x58: 88,      # JMP
}


def prototypes(data):
    stream = io.BytesIO(data)
    assert stream.read(5) == b"\x1bLJ\x02\x08"
    stream.read(read_uleb(stream))
    rows = []
    while length := read_uleb(stream):
        proto = io.BytesIO(stream.read(length))
        header = proto.read(4)
        gc_count, numbers, count, debug_size = (read_uleb(proto) for _ in range(4))
        if debug_size:
            read_uleb(proto)
            read_uleb(proto)
        code = [proto.read(4) for _ in range(count)]
        rows.append((header, gc_count, code))
    return rows


def test_chunk(code, gc_count, values, parameters, result, slots=12):
    translated = b"".join(bytes([OPCODES[word[0]]]) + word[1:] for word in code)
    translated += ad(76, result, 2)  # stock RET1
    constants = b"".join(
        uleb(5 + len(text)) + text
        for text in (values.get(i, b"unused") for i in reversed(range(gc_count)))
    )
    proto = (
        bytes([0, parameters, slots, 0]) + uleb(gc_count) + uleb(0)
        + uleb(len(code) + 1) + translated + constants
    )
    return b"\x1bLJ\x02\x0a" + uleb(len(proto)) + proto + b"\x00"


def verify(bundle, baseline=None):
    if not __debug__:
        raise ValueError("Run without -O.")
    from lupa.luajit21 import LuaRuntime

    runtime = LuaRuntime(encoding=None)
    execute = runtime.eval(
        b"function(code, env, ...) local f=assert(loadstring(code)); "
        b"setfenv(f,env); return f(...) end"
    )
    loadable = runtime.eval(b"function(s) local f,e=loadstring(s); return f~=nil,e end")
    modes = {key: i for i, key in enumerate(ENABLED_GAME_MODES, 1)}
    modes.update({b"GAMEMODE_PVP": 99, b"GAMEMODE_NULL": 0})
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8-sig"))
    old = None
    if baseline:
        old = json.loads((baseline / "manifest.json").read_text(encoding="utf-8-sig"))
        assert manifest["apk"] == old["apk"]
        assert manifest["files"] == old["files"]
    for entry in manifest["files"]:
        raw = (bundle / "payload" / entry["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["patched"]
        if baseline:
            assert raw == (baseline / "payload" / entry["path"]).read_bytes()
        data = decode(raw)
        assert loadable(data)[0]
        rows = prototypes(data)
        if entry["path"].endswith("/3543428409"):
            count = 7 + 5 * len(SINGLE_PLAYER_MODES)
            candidates = [row for row in rows if row[0][1] == 1 and len(row[2]) == 68 + count]
            assert len(candidates) == 1
            _, gc_count, full_code = candidates[0]
            code = full_code[40:40 + count]
            strings = (b"_gl", b"playerGameMode", b"gameMode") + SINGLE_PLAYER_MODES
            values = dict(zip(range(gc_count - len(strings), gc_count), strings))
            chunk = test_chunk(code, gc_count, values, 8, 7)
            for mode in list(modes.values()) + [None, 123]:
                gl = runtime.table_from({
                    b"playerGameMode": mode, b"gameMode": runtime.table_from(modes),
                })
                expected = 4096 if mode in range(1, len(SINGLE_PLAYER_MODES) + 1) else 160
                assert execute(chunk, runtime.table_from({b"_gl": gl}), *(0,) * 7, 160) == expected
        else:
            count = 16 + 5 * len(ENABLED_GAME_MODES)
            candidates = [row for row in rows if row[0][1] == 5 and len(row[2]) == 164 + count]
            assert len(candidates) == 1
            _, gc_count, full_code = candidates[0]
            values = {
                1: b"_gl", 14: b"gameMode", 13: b"playerGameMode",
                33: b"moneyChangeType", 34: b"MONEY_CHANGE_TOWER_SELL",
            }
            values.update(zip(range(gc_count - len(ENABLED_GAME_MODES), gc_count), ENABLED_GAME_MODES))
            chunk = test_chunk(full_code[:count], gc_count, values, 5, 1)
            for mode in list(modes.values()) + [None, 123]:
                gl = runtime.table_from({
                    b"playerGameMode": mode, b"gameMode": runtime.table_from(modes),
                    b"moneyChangeType": runtime.table_from({b"MONEY_CHANGE_TOWER_SELL": 3}),
                })
                env = runtime.table_from({b"_gl": gl})
                for amount, reason in [(40, None), (1, 1), (80, 3), (0, None), (-180, None)]:
                    eligible = mode in range(1, len(ENABLED_GAME_MODES) + 1)
                    expected = amount * 10 if eligible and amount > 0 and reason != 3 else amount
                    assert execute(chunk, env, None, amount, reason) == expected
            # Verify the root executes jit.off with this class's function and
            # recursive=true. This catches accidental removal of the stable fix.
            header, root_gc, root_code = rows[-1]
            scratch = header[2] - 4
            expected_ops = [0x3A, 0x0C, 0x3C, 0x0C, 0x3C, 0x10, 0x46]
            assert [word[0] for word in root_code[-8:-1]] == expected_ops
            assert root_code[-8] == ad(0x3A, scratch, root_gc - 3)
            assert root_code[-3] == ad(0x10, scratch + 3, 2)
            guard_values = dict(zip(
                range(root_gc - 3, root_gc), (b"jit", b"off", b"addGameLayerMoney")
            ))
            guard = test_chunk(root_code[-8:-1], root_gc, guard_values, 1, 0, header[2])
            calls = []
            target = runtime.eval(b"function() end")
            module = runtime.table_from({b"addGameLayerMoney": target})
            fake_jit = runtime.table_from({b"off": lambda fn, recursive: calls.append((fn, recursive))})
            execute(guard, runtime.table_from({b"jit": fake_jit}), module)
            assert len(calls) == 1 and calls[0][1] is True
            assert runtime.eval(b"function(a,b) return a==b end")(calls[0][0], target)
        print(f"PASS {entry['path']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    verify(args.bundle, args.baseline)


if __name__ == "__main__":
    main()
