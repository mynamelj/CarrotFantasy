import io
from bytecode_patch import read_uleb, uleb, ad, abc
def hook_chunk(data, source):
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
    return_slot=code[-1][1]
    base=header[2]
    assert base+3<250
    header[2]=base+3
    upvalues=root.read(header[3]*2)
    rest=root.read()
    constants=rest[:-dbg] if dbg else rest
    strings=(b'loadstring',source)
    added=b''.join(uleb(5+len(s))+s for s in reversed(strings))
    hook=[
        ad(0x3a,base,kgc),
        ad(0x0c,base+2,kgc+1),
        abc(0x46,base,2,2),
        ad(0x18,base+2,return_slot),
        abc(0x46,base,1,2),
    ]
    code[-1:-1]=hook
    new=(bytes(header)+uleb(kgc+len(strings))+uleb(kn)+uleb(len(code))+uleb(0)
         +b''.join(code)+upvalues+added+constants)
    prototypes[-1]=new
    for p in prototypes:
        result+=uleb(len(p))+p
    return bytes(result+b'\x00')
