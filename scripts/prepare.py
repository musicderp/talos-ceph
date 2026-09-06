#!/usr/bin/env python3
"""Apply narrow, checked customizations to the pinned upstream sources."""
import json
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1]
kind = sys.argv[1]
source = Path(sys.argv[2])

def replace_once(path, before, after):
    text = path.read_text()
    if text.count(before) != 1:
        raise SystemExit(f"Expected exactly one matching source block in {path}")
    path.write_text(text.replace(before, after))

if kind == "kernel":
    config = source / "kernel/build/config-amd64"
    for setting in ("CONFIG_CEPH_FS=y", "CONFIG_CEPH_LIB=y", "CONFIG_DRM_I915=m", "CONFIG_MODULE_SIG_ALL=y"):
        assert setting in config.read_text().splitlines(), setting
    replace_once(config, 'CONFIG_LOCALVERSION="-talos"', 'CONFIG_LOCALVERSION="-talos-ceph1"')
    shutil.copy2(root / "patches/0008-ceph-ignore-atime-flags.patch", source / "kernel/build/patches")
elif kind == "talos":
    modules = source / "hack/modules-amd64.txt"
    entries = set(modules.read_text().splitlines())
    entries.add("kernel/drivers/gpu/drm/i915/i915.ko")
    modules.write_text("\n".join(sorted(entries)) + "\n")
    dockerfile = source / "Dockerfile"
    marker = "COPY --link --from=modules-amd64 /usr/lib/modules /rootfs/usr/lib/modules"
    replace_once(dockerfile, marker, marker + "\nCOPY --link --from=pkg-linux-firmware /usr/lib/firmware/i915 /rootfs/usr/lib/firmware/i915")
    # Associate published images with this build repository, not the upstream repo.
    dockerfile.write_text(dockerfile.read_text().replace(
        "org.opencontainers.image.source=https://github.com/siderolabs/talos",
        "org.opencontainers.image.source=https://github.com/musicderp/talos-ceph"))
else:
    raise SystemExit("Usage: prepare.py kernel|talos SOURCE")
print(f"Prepared {kind}: {source}")
