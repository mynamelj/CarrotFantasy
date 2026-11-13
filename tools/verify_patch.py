"""Verify bundle hashes, mode behavior and the per-function JIT guard."""

import argparse
import hashlib
import io
import json
from pathlib import Path

from asset_codec import decode
from bytecode_patch import (
    COOP_MODE, ENABLED_GAME_MODES, OWNER_RANGE_KEYS, OWNER_SETTER_KEYS, RANGE_KEYS,
    SINGLE_PLAYER_MODES, abc, ad, owned_range_gate, read_uleb, uleb,
)


# These are this game's dump opcodes. Translate only the injected instructions
# into the stock LuaJIT 2.1 opcodes used by the host verification runtime.
OPCODES = {
    0x01: 1,       # ISGE
    0x04: 4,       # ISEQV
    0x05: 5,       # ISNEV
    0x0C: 39,      # KSTR
    0x0E: 41,      # KSHORT
    0x10: 43,      # KPRI
    0x12: 12,      # ISTC
    0x18: 18,      # MOV
    0x2C: 34,      # MULVV
    0x3A: 54,      # GGET
    0x3C: 56,      # TGETV
    0x3D: 57,      # TGETS
    0x41: 61,      # TSETS
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


def verify_build_selection(runtime, data, rows):
    load = runtime.eval(b"function(s) return assert(loadstring(s)) end")
    util = runtime.eval(b'require("jit.util")')
    module = load(data)
    assert util.funcinfo(module)[b"source"].endswith(b"/src/gamescene/ChessBoard.lua")
    header, gc_count, code = rows[-1]
    scratch = header[2] - 3
    assert util.funck(module, 1 - gc_count) == b"loadstring"
    assert code[-6:] == [
        ad(0x3A, scratch, gc_count - 2),
        ad(0x0C, scratch + 2, gc_count - 1),
        abc(0x46, scratch, 2, 2),
        ad(0x18, scratch + 2, code[-1][1]),
        abc(0x46, scratch, 1, 2),
        ad(0x1F, code[-1][1], 2),
    ]
    verify = runtime.eval(b"""function(source, solo_modes)
        local gl = {gameMode = {}, tower = {TOWER_SUN = 214, TOWER_CRYSTAL = 248}}
        for i, name in ipairs(solo_modes) do gl.gameMode[name] = i end
        gl.gameMode.GAMEMODE_COOPERATION = 9
        gl.gameMode.GAMEMODE_PVP = 10
        local proto = {['214_1'] = {}, ['248_1'] = {}}
        local env = setmetatable({_gl = gl, _data = {TowerData = {[214] = {}, [248] = {}}},
            _json = {turret_proto = proto}}, {__index = _G})
        local board = {getBuildSelectionIds = function(self)
            return {self.special, unpack(gl.inGameTowerIDList)}
        end, special = 42}
        local hook = assert(loadstring(source))
        setfenv(hook, env)(board)
        for mode = 0, 10 do
            gl.playerGameMode = mode
            local ids = {202, 203, 204, 205, 206}
            gl.inGameTowerIDList = ids
            local expected = mode >= 1 and mode <= #solo_modes
                and '42,202,203,204,205,206,214,248' or '42,202,203,204,205,206'
            for _ = 1, 2 do
                assert(table.concat(board:getBuildSelectionIds(), ',') == expected)
            end
            assert(#ids == 5)
        end
        gl.playerGameMode = 1
        local existing = {202, 214, 248}
        gl.inGameTowerIDList = existing
        assert(#board:getBuildSelectionIds() == 4 and gl.inGameTowerIDList == existing)
        gl.inGameTowerIDList = {202, 248}
        assert(table.concat(board:getBuildSelectionIds(), ',') == '42,202,248,214')
        gl.inGameTowerIDList = {202, 214}
        assert(table.concat(board:getBuildSelectionIds(), ',') == '42,202,214,248')
        gl.inGameTowerIDList = {202}
        proto['214_1'] = nil
        assert(table.concat(board:getBuildSelectionIds(), ',') == '42,202,248')
        gl.inGameTowerIDList = {202}
        proto['214_1'], proto['248_1'] = {}, nil
        assert(table.concat(board:getBuildSelectionIds(), ',') == '42,202,214')
    end""")
    verify(util.funck(module, -gc_count), runtime.table_from(SINGLE_PLAYER_MODES))


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
    coop_owned_range = manifest.get("coop_owned_range", False)
    old = None
    if baseline:
        old = json.loads((baseline / "manifest.json").read_text(encoding="utf-8-sig"))
        assert manifest["apk"] == old["apk"]
        assert manifest["files"] == old["files"]
    build_selection_found = False
    for entry in manifest["files"]:
        raw = (bundle / "payload" / entry["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["patched"]
        if baseline:
            assert raw == (baseline / "payload" / entry["path"]).read_bytes()
        data = decode(raw)
        assert loadable(data)[0]
        rows = prototypes(data)
        if entry["path"].endswith("/874078166"):
            verify_build_selection(runtime, data, rows)
            build_selection_found = True
        elif entry["path"].endswith("/3543428409"):
            count = 7 + 5 * len(SINGLE_PLAYER_MODES)
            strings = RANGE_KEYS + SINGLE_PLAYER_MODES
            if coop_owned_range:
                count += len(owned_range_gate(0))
                strings += OWNER_RANGE_KEYS
            candidates = [row for row in rows if row[0][1] == 1 and len(row[2]) == 68 + count]
            assert len(candidates) == 1
            header, gc_count, full_code = candidates[0]
            code = full_code[40:40 + count]
            values = dict(zip(range(gc_count - len(strings), gc_count), strings))
            chunk = test_chunk(code, gc_count, values, 8, 7, header[2])
            get_user_id = runtime.eval(b"function(self) return self.userId end")
            model = runtime.table_from({b"userId": 101, b"getUserId": get_user_id})
            data_model = runtime.table_from({b"DataModel": model})
            for mode in list(modes.values()) + [None, 123]:
                gl = runtime.table_from({
                    b"playerGameMode": mode, b"gameMode": runtime.table_from(modes),
                })
                env = runtime.table_from({b"_gl": gl, b"_data": data_model})
                for owner in (101, 202, 0, None):
                    eligible = mode in range(1, len(SINGLE_PLAYER_MODES) + 1) or (
                        coop_owned_range and mode == modes[COOP_MODE] and owner == 101
                    )
                    tower = runtime.table_from({b"ownerID": owner})
                    assert execute(chunk, env, tower, *(0,) * 6, 160) == (4096 if eligible else 160)
            if coop_owned_range:
                setters = [row for row in rows if row[0][1] == 2 and
                           row[1] == 1 + len(OWNER_SETTER_KEYS) and
                           row[2][:2] == [abc(0x3d, 3, 0, 0), ad(0x12, 2, 1)]]
                assert len(setters) == 1
                setter_header, setter_gc, setter_code = setters[0]
                setter_keys = dict(enumerate((b"ownerID",) + OWNER_SETTER_KEYS))
                setter = test_chunk(setter_code[:-1], setter_gc, setter_keys, 2, 0, setter_header[2])
                recalc = runtime.eval(b"function(self) self.refreshed = self.ownerID end")
                for mode, owner, new_owner, initialized, refreshed in (
                    (modes[COOP_MODE], 101, 202, True, 202),
                    (modes[COOP_MODE], 202, 101, True, 101),
                    (modes[COOP_MODE], 101, None, True, 0),
                    (modes[COOP_MODE], 101, 101, True, None),
                    (modes[COOP_MODE], 101, 202, False, None),
                    (modes[b"GAMEMODE_THEME"], 101, 202, True, None),
                ):
                    gl[b"playerGameMode"] = mode
                    tower = runtime.table_from({
                        b"ownerID": owner, b"json": {} if initialized else None, b"setShootRange": recalc,
                    })
                    execute(setter, env, tower, new_owner)
                    assert tower[b"ownerID"] == (new_owner or 0)
                    assert tower[b"refreshed"] == refreshed
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
            if manifest.get("no_donation_cooldown"):
                confirmations = [
                    row for row in rows if row[0][1:3] == bytes([1, 9]) and
                    row[1] == 16 and len(row[2]) == 26 and row[2][15] == abc(0x3d, 5, 0, 8)
                ]
                assert len(confirmations) == 1
                confirm_header, confirm_gc, confirm_code = confirmations[0]
                assert confirm_code[-1] == ad(0x1e, 0, 1)
                keys = (
                    b"_json", b"getActivityCooperationProto", b"_data", b"CooperationData",
                    b"getCurActivityId", b"tostring", b"coin_num", b"coin_cd",
                    b"cooperationDonateMoney", b"spBottomToolBar", b"donateMoneyButton",
                    b"startCoolingDown", b"setSelectedBtnIndex", b"_gl",
                    b"bottomToolBtnIndex", b"BTN_INDEX_NULL",
                )
                confirm = test_chunk(confirm_code[:-1], confirm_gc, dict(enumerate(keys)),
                                     1, 0, confirm_header[2])
                confirm_env, layer = runtime.eval(b"""(function()
                    local toolbar = {
                        donateMoneyButton = {startCoolingDown = function() error("cooldown") end},
                        setSelectedBtnIndex = function(self, index) self.selection = index end,
                    }
                    local env = {
                        _json = {getActivityCooperationProto = function()
                            return {["17"] = {coin_num = 300, coin_cd = 60}}
                        end},
                        _data = {CooperationData = {getCurActivityId = function() return 17 end}},
                        _gl = {bottomToolBtnIndex = {BTN_INDEX_NULL = 0}},
                        tostring = tostring,
                    }
                    local layer = {
                        spBottomToolBar = toolbar,
                        sent = 0,
                        cooperationDonateMoney = function(self, amount) self.sent = self.sent + amount end,
                    }
                    return env, layer
                end)()""")
                for amount in (300, 600):
                    layer[b"spBottomToolBar"][b"selection"] = 1
                    execute(confirm, confirm_env, layer)
                    assert layer[b"sent"] == amount
                    assert layer[b"spBottomToolBar"][b"selection"] == 0
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
    assert build_selection_found == manifest.get("append_sunflower", False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    verify(args.bundle, args.baseline)


if __name__ == "__main__":
    main()
