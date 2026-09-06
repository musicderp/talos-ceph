"""Check the effective upstream Ceph source before adding our downstream patch."""
import hashlib
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PATCH_NAME = "9999-ceph-ignore-atime-flags.patch"
REQUIRED = {"SB_BORN", "SB_NODIRATIME", "SB_NOATIME"}


def masked_flags(source):
    start = source.index("static int ceph_compare_super(")
    function = source[start:source.index("\n}", start)]
    match = re.search(r"fc->sb_flags\s*!=\s*\(sb->s_flags\s*&\s*~(\([^)]*\)|SB_BORN)\)", function)
    if not match:
        raise ValueError("Ceph superblock comparison changed; patch review required")
    expression = match[1]
    flags = set(re.findall(r"\bSB_[A-Z_]+\b", expression))
    if re.sub(r"SB_[A-Z_]+|[\s()|]", "", expression):
        raise ValueError("Unexpected Ceph flag expression; review required")
    return flags


def patch_state(source):
    flags = masked_flags(source)
    active = re.search(r"s_flags\s*(?:\|=|=)[^;]*\bSB_ACTIVE\b", source)
    required = REQUIRED | ({"SB_ACTIVE"} if active else set())
    if required <= flags:
        return "upstream"
    if flags == {"SB_BORN"} and not active:
        return "apply"
    raise ValueError("Ceph flags, including possible SB_ACTIVE handling, need patch review")


def prepare(source, versions):
    pkgfile = (source / "Pkgfile").read_text()
    match = re.search(r"(?m)^\s*linux_sha256:\s*([a-f0-9]{64})\s*$", pkgfile)
    if not match:
        raise ValueError("Kernel checksum missing from upstream Pkgfile")
    checksum = match[1]
    if versions.get("KERNEL_SHA256", checksum) != checksum:
        raise ValueError("Kernel checksum differs from pinned versions.env")
    version = versions["KERNEL_VERSION"]
    if not re.search(r"(?m)^\s*linux_version:\s*" + re.escape(version) + r"\s*$", pkgfile):
        raise ValueError("Kernel version differs from pinned versions.env")
    cache = ROOT / "work" / f"linux-{version}.tar.xz"
    cache.parent.mkdir(exist_ok=True)
    if not cache.exists():
        url = f"https://cdn.kernel.org/pub/linux/kernel/v{version.split('.')[0]}.x/linux-{version}.tar.xz"
        with urllib.request.urlopen(url, timeout=120) as response, cache.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    with cache.open("rb") as archive:
        actual = hashlib.file_digest(archive, "sha256").hexdigest()
    if actual != checksum:
        cache.unlink()
        raise ValueError("Kernel archive checksum mismatch; removed invalid download")
    patch_dir = source / "kernel/build/patches"
    destination = patch_dir / PATCH_NAME
    if destination.exists():
        raise ValueError("Custom patch destination already exists; use a fresh upstream checkout")
    with tempfile.TemporaryDirectory() as temporary:
        tree = Path(temporary)
        target = tree / "fs/ceph/super.c"
        target.parent.mkdir(parents=True)
        with tarfile.open(cache) as archive:
            target.write_bytes(archive.extractfile(f"linux-{version}/fs/ceph/super.c").read())
        # Match the upstream sorted patch order, examining only the relevant file.
        for patch in sorted(patch_dir.rglob("*.patch")):
            subprocess.run(["git", "apply", "--include=fs/ceph/super.c", str(patch.resolve())], cwd=tree, check=True)
        state = patch_state(target.read_text())
        if state == "apply":
            patch = ROOT / "patches/0008-ceph-ignore-atime-flags.patch"
            subprocess.run(["git", "apply", "--check", str(patch)], cwd=tree, check=True)
            subprocess.run(["git", "apply", str(patch)], cwd=tree, check=True)
            if patch_state(target.read_text()) != "upstream":
                raise ValueError("Ceph patch did not establish the expected flag mask")
            destination.write_bytes(patch.read_bytes())
        result = f"Ceph fix: {state}; verified Linux {version} archive sha256:{checksum}\n"
        (source / "ceph-patch-status.txt").write_text(result)
        print(result, end="")
