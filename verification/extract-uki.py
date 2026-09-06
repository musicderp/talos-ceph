import pathlib,struct
p=pathlib.Path('./vmlinuz.efi').read_bytes()
assert p[:2]==b'MZ'
pe=struct.unpack_from('<I',p,0x3c)[0]
assert p[pe:pe+4]==b'PE\0\0'
n=struct.unpack_from('<H',p,pe+6)[0]
opt=struct.unpack_from('<H',p,pe+20)[0]
start=pe+24+opt
for i in range(n):
 off=start+40*i
 name=p[off:off+8].rstrip(b'\0').decode()
 virtual_size=struct.unpack_from('<I',p,off+8)[0]
 size,offset=struct.unpack_from('<II',p,off+16)
 size=min(size,virtual_size) if virtual_size else size
 assert offset+size <= len(p)
 if name in ('.linux','.initrd','.uname','.cmdline'):
  pathlib.Path('./'+name[1:]).write_bytes(p[offset:offset+size])
  print(name,size)
