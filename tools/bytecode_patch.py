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

RANGE_KEYS = (b'_gl', b'playerGameMode', b'gameMode')
COOP_MODE = b'GAMEMODE_COOPERATION'
OWNER_RANGE_KEYS = (COOP_MODE, b'ownerID', b'_data', b'DataModel', b'getUserId')
OWNER_SETTER_KEYS = RANGE_KEYS + (COOP_MODE, b'json', b'setShootRange')
DONATION_CONFIRM_LINES = {3563: 5259, 3569: 5269}


def owned_range_gate(kgc):
    first = kgc + len(RANGE_KEYS) + len(SINGLE_PLAYER_MODES)
    coop, owner, data, model, user_id = range(first, first + len(OWNER_RANGE_KEYS))
    body = [
        abc(0x3d, 9, 0, owner),
        ad(0x10, 8, 0),              # nil
        ad(0x04, 9, 8),
        jump(3, 16, 8),
        ad(0x0e, 8, 0),
        ad(0x04, 9, 8),
        jump(6, 16, 8),
        ad(0x3a, 8, data),
        abc(0x3d, 8, 8, model),
        ad(0x18, 10, 8),             # DataModel self, after the FR2 slot
        abc(0x3d, 8, 8, user_id),
        abc(0x46, 8, 2, 2),
        abc(0x3d, 9, 0, owner),
        ad(0x05, 8, 9),             # ISNEV
        jump(14, 16, 8),
        ad(0x0e, 7, 4096),
    ]
    return mode_gate(8, 9, kgc, kgc + 1, kgc + 2, (coop,), body)


def code_patch(proto, expected_line, coop_owned_range=False, donation_line=None):
    stream = io.BytesIO(proto)
    header = stream.read(4)
    kgc, kn, nb, dbg = (read_uleb(stream) for _ in range(4))
    line = read_uleb(stream) if dbg else None
    owner_setter = coop_owned_range and line == 608
    donation_confirm = donation_line is not None and line == donation_line
    if line != expected_line and not owner_setter and not donation_confirm:
        return proto, False
    read_uleb(stream)  # last line delta
    code = [stream.read(4) for _ in range(nb)]
    upvalues = stream.read(header[3] * 2)
    constants = stream.read()[:-dbg]

    if donation_confirm:
        assert header[1:3] == bytes([1, 9]) and kgc == 16 and nb == 36
        assert not any(word[0] == 0x58 for word in code)
        assert code[14:19] == [
            ad(0x3a, 4, 5), ad(0x18, 6, 2), abc(0x46, 4, 2, 2),
            abc(0x3c, 4, 1, 4), abc(0x3d, 4, 4, 7),  # coin_cd
        ]
        assert code[23:28] == [
            abc(0x3d, 5, 0, 9), abc(0x3d, 5, 5, 10), ad(0x18, 7, 5),
            abc(0x3d, 5, 5, 11), abc(0x46, 5, 1, 2),  # startCoolingDown
        ]
        # Keep the normal transfer and deselection, which resets the open button.
        strings = ()
        code = code[:14] + code[19:23] + code[28:]
    elif owner_setter:
        assert header[1] == 2 and kgc == 1
        assert code == [ad(0x12, 2, 1), jump(1, 3, 2), ad(0x0e, 2, 0),
                        abc(0x41, 2, 0, 0), ad(0x1e, 0, 1)]
        strings = OWNER_SETTER_KEYS
        refresh = [
            abc(0x3d, 2, 0, kgc + 4),  # json assigned by the initial range calculation
            ad(0x10, 3, 0),
            ad(0x04, 2, 3),
            jump(3, 7, 2),
            ad(0x18, 4, 0),
            abc(0x3d, 2, 0, kgc + 5),
            abc(0x46, 2, 1, 2),
        ]
        gate = mode_gate(2, 3, kgc, kgc + 1, kgc + 2, (kgc + 3,), refresh)
        unchanged = [ad(0x04, 3, 2), jump(1, 2 + len(gate), 2)]
        code = [abc(0x3d, 3, 0, 0)] + code[:-1] + unchanged + gate + code[-1:]
        header = header[:2] + bytes([5]) + header[3:]
    elif header[1] == 5:
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
        strings = RANGE_KEYS + SINGLE_PLAYER_MODES
        gate = mode_gate(8, 9, kgc, kgc + 1, kgc + 2,
                                  range(kgc + 3, kgc + len(strings)),
                                  [ad(0x0e, 7, 4096)])
        if coop_owned_range:
            strings += OWNER_RANGE_KEYS
            gate += owned_range_gate(kgc)
            header = header[:2] + bytes([11]) + header[3:]
        code[40:40] = gate

    # KGC entries are written from highest to lowest index.
    added = b''.join(uleb(5 + len(s)) + s for s in reversed(strings))
    new = (header + uleb(kgc + len(strings)) + uleb(kn) + uleb(len(code))
           + uleb(0) + b''.join(code) + upvalues + added + constants)
    return new, True

def patch_chunk(data, line, coop_owned_range=False, no_donation_cooldown=False):
    stream = io.BytesIO(data)
    assert stream.read(5) == b'\x1bLJ\x02\x08'
    stream.read(read_uleb(stream))
    result = bytearray(data[:stream.tell()])
    changed = 0
    donation_line = DONATION_CONFIRM_LINES[line] if no_donation_cooldown else None
    while (length := read_uleb(stream)):
        proto = stream.read(length)
        new_proto, did_change = code_patch(proto, line, coop_owned_range, donation_line)
        changed += did_change
        result += uleb(len(new_proto)) + new_proto
    assert changed == 1 + coop_owned_range + no_donation_cooldown and stream.read() == b''
    return bytes(result + b'\x00')

