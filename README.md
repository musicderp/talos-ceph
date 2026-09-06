# Talos with the CephFS superblock-sharing fix

Builds an amd64 Talos v1.13.6 installer on GitHub Actions and publishes to
`ghcr.io/musicderp/talos-ceph/installer`. Upstream Talos and package commits are
pinned in `versions.env`; each build also gets a source-commit tag. Deploy by
image digest to keep the installed artifact immutable.

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

After a successful build, a second workflow extracts the installer's boot image
and verifies its embedded kernel configuration, Ceph builtins, i915 module,
firmware, module dependencies, and appended module signatures. It publishes a
GitHub release containing a Docker image archive, SHA256 checksum, image digest,
kernel configuration, and verification report. Live boot and CephFS sharing
validation are performed separately on the target cluster.

Live validation confirmed that two read-only static CephFS PVs pointing to the
same directory share a superblock with this kernel; the stock kernel gave them
different device IDs. i915 loaded with signature enforcement enabled.
The installer was deployed sequentially to six amd64 nodes; all passed kernel,
GPU, workload, and Ceph health checks after reboot.

There is a separate Kubernetes lifecycle limitation when different static PV
volume handles point to the same CephFS directory. After sharing is restored,
kubelet's `GetDeviceMountRefs` check can mistake other PV staging mounts for
references to an unused volume and prevent `NodeUnstageVolume`. This was
reproduced during test cleanup and matches
[Kubernetes #105323](https://github.com/kubernetes/kubernetes/issues/105323).
Pods can run while unused staging mounts and VolumeAttachments remain. The
kernel patch does not fix this kubelet behavior. Cleanup of the validation
volumes required normal unmounts of only their confirmed-unused staging paths;
production mounts were preserved. Account for this limitation before adopting
this image for duplicate static PVs; a general kubelet/CSI fix is separate work.

The source patch is GPL-2.0-only as part of the Linux kernel. Upstream source
licenses continue to apply. This repository does not submit the patch upstream.
