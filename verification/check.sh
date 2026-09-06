#!/bin/bash
set -euo pipefail
VERIFY_DIR=$(pwd)
python3 ./extract-uki.py
python3 - <<'PY'
from pathlib import Path
args=Path('cmdline').read_bytes().rstrip(b'\0').decode().split()
assert 'module.sig_enforce=1' in args, 'Signature enforcement missing'
assert not any(a.startswith('talos.experimental.wipe=') for a in args), 'Default boot profile would wipe disks'
print('Default boot profile enforces module signatures and has no wipe argument')
PY
bash ./extract-ikconfig ./linux > ./kernel.config
grep -Fx CONFIG_CEPH_FS=y ./kernel.config
grep -Fx CONFIG_CEPH_LIB=y ./kernel.config
grep -Fx CONFIG_DRM_I915=m ./kernel.config
grep -Fx CONFIG_MODULE_SIG_ALL=y ./kernel.config
mkdir -p ./initramfs
cd "$VERIFY_DIR/initramfs"
zstd -dc ../initrd | cpio -id --quiet
unsquashfs -d "$VERIFY_DIR/rootfs" rootfs.sqsh >"$VERIFY_DIR/unsquashfs.log"
cd "$VERIFY_DIR"
release=6.18.38-talos-ceph1
test -d "rootfs/usr/lib/modules/$release"
i915="rootfs/usr/lib/modules/$release/kernel/drivers/gpu/drm/i915/i915.ko"
test -s "$i915"
modinfo -F vermagic "$i915" | grep -F "$release"
test -n "$(modinfo -F signer "$i915")"
grep -F 'kernel/fs/ceph/ceph.ko' "rootfs/usr/lib/modules/$release/modules.builtin"
grep -F 'kernel/net/ceph/libceph.ko' "rootfs/usr/lib/modules/$release/modules.builtin"
test -n "$(find rootfs/usr/lib/firmware/i915 -type f -print -quit)"
modprobe -d ./rootfs/usr -S "$release" --show-depends i915
python3 - <<'PY'
from pathlib import Path
mods=list(Path('rootfs/usr/lib/modules').rglob('*.ko'))
unsigned=[str(p) for p in mods if not p.read_bytes().endswith(b'~Module signature appended~\n')]
assert not unsigned,unsigned
print(f'All {len(mods)} packaged modules have appended signatures')
PY
printf 'INSTALLER_CONTENTS_VERIFIED\n'
