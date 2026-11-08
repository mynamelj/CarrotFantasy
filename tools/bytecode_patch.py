"""Version-specific bytecode edits for the tested LuaJIT dump format."""

import io

def read_uleb(stream):
    value = 0
    for shift in range(0, 35, 7):
        byte = stream.read(1)[0]
        value |= (byte & 127) << shift
        if byte < 128:
            return value
    raise ValueError('invalid ULEB')

def uleb(value):
    parts = bytearray()
    while value > 127:
        parts.append((value & 127) | 128)
        value >>= 7
    parts.append(value)
    return parts

def ad(op, a, d):
    return bytes((op, a, d & 255, d >> 8))

def abc(op, a, b, c):
    return bytes((op, a, c, b))

def jump(pc, target, base):
    return ad(0x58, base, 32768 + target - pc - 1)

SINGLE_PLAYER_MODES = (
    b'GAMEMODE_THEME',
    b'GAMEMODE_WEEKLY',
    b'GAMEMODE_WEEKLY_LOCAL',
    b'GAMEMODE_DAILY_MATCH',
    b'GAMEMODE_STAR_WAY',
    b'GAMEMODE_CANDY',
    b'GAMEMODE_COLLECT',
)

ENABLED_GAME_MODES = SINGLE_PLAYER_MODES + (b'GAMEMODE_COOPERATION',)

def mode_gate(mode, scratch, global_key, player_mode_key,
                       game_mode_key, allowed_keys, body):
    code = [
        ad(0x3a, mode, global_key),
        abc(0x3d, mode, mode, player_mode_key),
        ad(0x10, scratch, 0),             # KPRI nil
        ad(0x04, mode, scratch),          # ISEQV
        b'',
    ]
    matches = []
    for key in allowed_keys:
        code.extend([
            ad(0x3a, scratch, global_key),
            abc(0x3d, scratch, scratch, game_mode_key),
            abc(0x3d, scratch, scratch, key),
            ad(0x04, mode, scratch),
            b'',
        ])
        matches.append(len(code) - 1)

    body_start = len(code) + 1
    end = body_start + len(body)
    code[4] = jump(4, end, mode)
    for pc in matches:
        code[pc] = jump(pc, body_start, mode)
    return code + [jump(len(code), end, mode)] + body

def code_patch(proto, expected_line):
    stream = io.BytesIO(proto)
    header = stream.read(4)
    kgc, kn, nb, dbg = (read_uleb(stream) for _ in range(4))
    line = read_uleb(stream) if dbg else None
    if line != expected_line:
        return proto, False
    read_uleb(stream)  # last line delta
    code = [stream.read(4) for _ in range(nb)]
    upvalues = stream.read(header[3] * 2)
    constants = stream.read()[:-dbg]

    if header[1] == 5:
        assert nb == 164
        assert code[21] == abc(0x3d, 5, 0, 7)
        # The original amount remains intact for spending and tower refunds.
        strings = ENABLED_GAME_MODES
        body = [ad(0x0e, 5, 10), abc(0x2c, 1, 1, 5)]
        gate = mode_gate(5, 6, 1, 13, 14,
                                  range(kgc, kgc + len(strings)), body)
        prefix = [
            ad(0x0e, 5, 0),
            ad(0x01, 5, 1),             # ISGE
            jump(2, 8 + len(gate), 5),
            ad(0x3a, 5, 1),             # _gl
            abc(0x3d, 5, 5, 33),        # moneyChangeType
            abc(0x3d, 5, 5, 34),        # MONEY_CHANGE_TOWER_SELL
            ad(0x04, 2, 5),             # ISEQV
            jump(7, 8 + len(gate), 5),
        ]
        code = prefix + gate + code
    else:
        assert nb == 68 and header[1] == 1
        assert code[39] == abc(0x2c, 7, 3, 7) and code[40] == bytes.fromhex('46040301')
        assert not any(i[0] == 0x58 for i in code)
        strings = (b'_gl', b'playerGameMode', b'gameMode') + SINGLE_PLAYER_MODES
        gate = mode_gate(8, 9, kgc, kgc + 1, kgc + 2,
                                  range(kgc + 3, kgc + len(strings)),
                                  [ad(0x0e, 7, 4096)])
        code[40:40] = gate

    # KGC entries are written from highest to lowest index.
    added = b''.join(uleb(5 + len(s)) + s for s in reversed(strings))
    new = (header + uleb(kgc + len(strings)) + uleb(kn) + uleb(len(code))
           + uleb(0) + b''.join(code) + upvalues + added + constants)
    return new, True

def patch_chunk(data, line):
    stream = io.BytesIO(data)
    assert stream.read(5) == b'\x1bLJ\x02\x08'
    stream.read(read_uleb(stream))
    result = bytearray(data[:stream.tell()])
    changed = 0
    while (length := read_uleb(stream)):
        proto = stream.read(length)
        new_proto, did_change = code_patch(proto, line)
        changed += did_change
        result += uleb(len(new_proto)) + new_proto
    assert changed == 1 and stream.read() == b''
    return bytes(result + b'\x00')

