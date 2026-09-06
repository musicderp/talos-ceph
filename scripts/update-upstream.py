#!/usr/bin/env python3
"""Pin the highest published stable Talos release and its exact build inputs."""
import argparse
import json
import os
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STABLE = re.compile(r"v(\d+)\.(\d+)\.(\d+)")


def read_versions(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines()
                if line and not line.startswith("#"))


def fetch(url):
    headers = {"User-Agent": "talos-ceph-upstream-sync"}
    if url.startswith("https://api.github.com/") and os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read().decode()


def api(path):
    return json.loads(fetch("https://api.github.com/repos/" + path))


def latest_stable(releases):
    candidates = [r["tag_name"] for r in releases
                  if not r["draft"] and not r["prerelease"] and STABLE.fullmatch(r["tag_name"])]
    if not candidates:
        raise ValueError("No published stable Talos release found")
    return max(candidates, key=lambda tag: tuple(map(int, STABLE.fullmatch(tag).groups())))


def package_ref(version):
    if not re.fullmatch(r"v[0-9A-Za-z.+-]+", version):
        raise ValueError("Unexpected upstream package version")
    match = re.search(r"-g([a-f0-9]{7,40})$", version)
    return match[1] if match else version


def field(text, name, pattern):
    matches = re.findall(r"(?m)^\s*" + re.escape(name) + r":\s*([^\s]+)\s*$", text)
    if len(matches) != 1 or not re.fullmatch(pattern, matches[0]):
        raise ValueError("Unexpected upstream field: " + name)
    return matches[0]


def resolve(current):
    releases = []
    page = 1
    while True:
        batch = api(f"siderolabs/talos/releases?per_page=100&page={page}")
        releases.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    version = latest_stable(releases)
    previous = STABLE.fullmatch(current.get("TALOS_VERSION", ""))
    if previous and tuple(map(int, STABLE.fullmatch(version).groups())) < tuple(map(int, previous.groups())):
        raise ValueError("Latest upstream release is older than the current pin; refusing downgrade")
    commit = api(f"siderolabs/talos/commits/{version}")["sha"]
    if current.get("TALOS_VERSION") == version and current["TALOS_COMMIT"] != commit:
        raise ValueError("Upstream moved an already pinned release tag; review required")
    prefix = f"https://raw.githubusercontent.com/siderolabs/talos/{commit}/"
    package = fetch(prefix + "pkg/machinery/gendata/data/pkgs").strip()
    package_commit = api("siderolabs/pkgs/commits/" + package_ref(package))["sha"]
    for sha in (commit, package_commit):
        if not re.fullmatch(r"[a-f0-9]{40}", sha):
            raise ValueError("Upstream did not resolve to a full commit SHA")
    pkgfile = fetch(f"https://raw.githubusercontent.com/siderolabs/pkgs/{package_commit}/Pkgfile")
    kernel = field(pkgfile, "linux_version", r"\d+\.\d+(?:\.\d+)?")
    image_tag = current.get("IMAGE_TAG") if current.get("TALOS_VERSION") == version else f"{version}-ceph.1"
    return dict(TALOS_VERSION=version, TALOS_COMMIT=commit, PKGS_VERSION=package,
                PKGS_COMMIT=package_commit, KERNEL_VERSION=kernel,
                KERNEL_RELEASE=kernel + "-talos-ceph1", IMAGE_TAG=image_tag,
                KERNEL_SHA256=field(pkgfile, "linux_sha256", r"[a-f0-9]{64}"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Resolve and display pins without writing")
    args = parser.parse_args()
    path = ROOT / "versions.env"
    current = read_versions(path)
    updated = resolve(current)
    content = "".join(f"{key}={value}\n" for key, value in updated.items())
    print(content, end="")
    changed = current != updated
    if changed and not args.check:
        path.write_text(content)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"changed={str(changed).lower()}\nversion={updated['TALOS_VERSION']}\n")


if __name__ == "__main__":
    main()
