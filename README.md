# Talos with the CephFS superblock-sharing fix

Builds an amd64 Talos v1.13.6 installer on GitHub Actions and publishes to
`ghcr.io/musicderp/talos-ceph/installer`. Upstream Talos and package commits are
pinned in `versions.env`; each build also gets an immutable source-commit tag.

The Linux 6.18.38 CephFS comparison incorrectly treats the client's own no-atime
superblock flags as mount-option differences. The included patch masks these
flags so otherwise compatible mounts can share a superblock and client.
This kernel does not contain the later SB_ACTIVE change discussed in the patch.

CephFS (`CONFIG_CEPH_FS=y`) and libceph (`CONFIG_CEPH_LIB=y`) remain built into
the kernel. Intel i915 is compiled and signed in the same kernel build. Its
module is included in the initramfs with the standard Talos DRM dependencies
and the matching upstream i915 firmware. Do not add the stock i915 extension:
its module is signed by a different kernel-build key.

Kernel release: `6.18.38-talos-ceph1`. Talos userspace stays v1.13.6.
The workflow requires no personal access token and receives no cluster secrets.
Deployment is a separate authenticated rolling Talos upgrade from a management
workstation, one node at a time, with Kubernetes and Ceph health checks.

The source patch is GPL-2.0-only as part of the Linux kernel. Upstream source
licenses continue to apply. This repository does not submit the patch upstream.
