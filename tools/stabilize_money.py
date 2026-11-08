from bytecode_patch import read_uleb, uleb, ad, abc
import io

def stabilize_money(data):
    stream=io.BytesIO(data)
    assert stream.read(5)==b'\x1bLJ\x02\x08'
    stream.read(read_uleb(stream))
    result=bytearray(data[:stream.tell()])
    prototypes=[]
    while length:=read_uleb(stream):
        prototypes.append(stream.read(length))
    assert not stream.read()
    root=io.BytesIO(prototypes[-1])
    header=bytearray(root.read(4))
    kgc,kn,nb,dbg=(read_uleb(root) for _ in range(4))
    if dbg:
        read_uleb(root);read_uleb(root)
    code=[root.read(4) for _ in range(nb)]
    assert code[-1][0]==0x1f and int.from_bytes(code[-1][2:],'little')==2
    module=code[-1][1]
    scratch=header[2]
    header[2]=scratch+4
    upvalues=root.read(header[3]*2)
    rest=root.read()
    constants=rest[:-dbg] if dbg else rest
    strings=(b'jit',b'off',b'addGameLayerMoney')
    added=b''.join(uleb(5+len(s))+s for s in reversed(strings))
    hook=[
        ad(0x3a,scratch,kgc),                   # GGET jit
        ad(0x0c,scratch+1,kgc+1),               # KSTR off
        abc(0x3c,scratch,scratch,scratch+1),     # TGETV
        ad(0x0c,scratch+2,kgc+2),               # KSTR addGameLayerMoney
        abc(0x3c,scratch+2,module,scratch+2),    # TGETV
        ad(0x10,scratch+3,2),                   # KPRI true
        abc(0x46,scratch,1,3),                  # CALL jit.off(fn,true)
    ]
    code[-1:-1]=hook
    new=(bytes(header)+uleb(kgc+len(strings))+uleb(kn)+uleb(len(code))+uleb(0)
         +b''.join(code)+upvalues+added+constants)
    prototypes[-1]=new
    for proto in prototypes:
        result+=uleb(len(proto))+proto
    return bytes(result+b'\x00')

