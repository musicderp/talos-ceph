# Talos with the CephFS superblock-sharing fix

Builds an amd64 installer for the latest stable Talos release on GitHub Actions and publishes to
`ghcr.io/musicderp/talos-ceph/installer`. Upstream Talos and package commits are
pinned in `versions.env`; each build also gets a source-commit tag. Deploy by
image digest to keep the installed artifact immutable.

The affected Linux CephFS comparison incorrectly treats the client's own no-atime
superblock flags as mount-option differences. The included patch masks these
flags so otherwise compatible mounts can share a superblock and client.
Before building, the automation verifies the kernel archive checksum, applies
upstream patches to the Ceph source, and checks the comparison. It skips our
patch when upstream already contains the fix and stops for review if the
comparison or SB_ACTIVE handling has changed incompatibly.

CephFS (`CONFIG_CEPH_FS=y`) and libceph (`CONFIG_CEPH_LIB=y`) remain built into
the kernel. Intel i915 is compiled and signed in the same kernel build. Its
module is included in the initramfs with the standard Talos DRM dependencies
and the matching upstream i915 firmware. Do not add the stock i915 extension:
its module is signed by a different kernel-build key.

Current target: Talos `v1.14.0`, Linux `6.18.48-talos-ceph1`.
`versions.env` is authoritative as new stable releases appear.
The workflow requires no personal access token and receives no cluster secrets.
Deployment is a separate authenticated rolling Talos upgrade from a management
workstation, one node at a time, with Kubernetes and Ceph health checks.

After a successful build, a second workflow extracts the installer's boot image
and verifies its embedded kernel configuration, Ceph builtins, i915 module,
firmware, module dependencies, and appended module signatures. It publishes a
GitHub release containing a Docker image archive, SHA256 checksum, image digest,
kernel configuration, and verification report. Live boot and CephFS sharing
validation are performed separately on the target cluster.

The initial Talos v1.13.6 / Linux 6.18.38 build was validated live. Testing confirmed that two read-only static CephFS PVs pointing to the
same directory share a superblock with this kernel; the stock kernel gave them
different device IDs. i915 loaded with signature enforcement enabled.
That initial installer was deployed sequentially to six amd64 nodes; all passed kernel,
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

## Automatic stable tracking

`Track stable Talos releases` checks upstream daily at 06:23 UTC and can also be
run manually. It selects the highest published `vMAJOR.MINOR.PATCH` release,
excluding drafts, prereleases, and machinery-module tags. A newly published
maintenance release on an older branch cannot move the target backward.

The updater resolves the Talos release to its exact commit, reads that commit's
package pin, resolves the package commit, and derives its kernel version and
checksum. It validates patch and i915 source compatibility before committing
`versions.env`. It then explicitly dispatches the build using `GITHUB_TOKEN`;
GitHub does not trigger push workflows for commits made with that token.
No personal token is required.

New images retain the Ceph fix, built-in CephFS/libceph, and matching signed i915.
Every successful build triggers boot-image verification and a downloadable
release. Only verified builds whose inputs still match main are promoted to
`ghcr.io/musicderp/talos-ceph/installer:stable` and `:latest`. Each release also
has a commit-specific tag and digest. The last verified aliases remain usable
if an upstream change breaks compilation or validation.

Failures are reported through GitHub Actions and require investigation; the
updater does not discard a patch that no longer applies. Rerun a failed job, or
run the tracking workflow with `force_build` to rebuild unchanged pins. Scheduled
workflows in public repositories may be disabled by GitHub after 60 days with
no repository activity; re-enable the schedule in Actions if that happens.

This repository is a build overlay over pinned upstream source, not a GitHub
fork with a periodically merged copy of the full Talos source tree. Tracking
stable releases keeps all upstream source changes in each release while
applying the narrow customizations here. It does not follow unreleased main
commits or automatically upgrade a cluster. The existing deployment remains
pinned to its validated digest until a separate rolling upgrade is requested.

Local checks:

```bash
python3 -B -m unittest discover -s tests -v
python3 -B scripts/update-upstream.py --check
```
