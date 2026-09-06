import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from ceph_patch import patch_state

spec = importlib.util.spec_from_file_location("upstream", SCRIPTS / "update-upstream.py")
upstream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upstream)


def release(tag, prerelease=False, draft=False):
    return dict(tag_name=tag, prerelease=prerelease, draft=draft)


def ceph(mask="SB_BORN", active=False):
    return ("static int ceph_compare_super(struct super_block *sb, struct fs_context *fc)\n{\n"
            f" if (fc->sb_flags != (sb->s_flags & ~{mask})) return 0;\n}}\n"
            + ("sb->s_flags |= SB_ACTIVE;\n" if active else ""))


class StableSelection(unittest.TestCase):
    def test_recent_maintenance_does_not_downgrade(self):
        self.assertEqual(upstream.latest_stable([
            release("v1.12.12"), release("v1.14.0"), release("v1.13.10")]), "v1.14.0")

    def test_prereleases_drafts_and_submodules_are_excluded(self):
        self.assertEqual(upstream.latest_stable([
            release("v1.15.0-rc.1", True), release("v1.15.0", draft=True),
            release("pkg/machinery/v2.0.0"), release("v1.14.0")]), "v1.14.0")

    def test_numeric_not_lexical_order(self):
        self.assertEqual(upstream.latest_stable([
            release("v1.13.9"), release("v1.13.10")]), "v1.13.10")

    def test_no_release_fails(self):
        with self.assertRaises(ValueError):
            upstream.latest_stable([release("v2.0.0-alpha.0", True)])

    def test_withdrawn_release_does_not_downgrade_current_pin(self):
        with patch.object(upstream, "api", return_value=[release("v1.13.10")]):
            with self.assertRaisesRegex(ValueError, "refusing downgrade"):
                upstream.resolve({"TALOS_VERSION": "v1.14.0"})

    def test_retargeted_release_requires_review(self):
        with patch.object(upstream, "api", side_effect=[[release("v1.14.0")], {"sha": "b" * 40}]):
            with self.assertRaisesRegex(ValueError, "moved an already pinned"):
                upstream.resolve({"TALOS_VERSION": "v1.14.0", "TALOS_COMMIT": "a" * 40})

    def test_package_commit_from_describe_or_release(self):
        self.assertEqual(upstream.package_ref("v1.14.0-15-g2f03590"), "2f03590")
        self.assertEqual(upstream.package_ref("v1.14.0"), "v1.14.0")
        with self.assertRaises(ValueError):
            upstream.package_ref("v1.14.0\nEVIL=value")


class PatchCompatibility(unittest.TestCase):
    def test_original_regression_needs_patch(self):
        self.assertEqual(patch_state(ceph()), "apply")

    def test_upstream_fix_is_not_double_applied(self):
        self.assertEqual(patch_state(ceph("(SB_BORN | SB_NODIRATIME | SB_NOATIME)")), "upstream")

    def test_active_flag_requires_review(self):
        for mask in ["SB_BORN", "(SB_BORN | SB_NODIRATIME | SB_NOATIME)"]:
            with self.assertRaises(ValueError):
                patch_state(ceph(mask, active=True))

    def test_complete_upstream_fix_with_active_is_accepted(self):
        self.assertEqual(patch_state(ceph("(SB_BORN | SB_ACTIVE | SB_NODIRATIME | SB_NOATIME)", True)), "upstream")

    def test_unknown_comparison_stops_instead_of_publishing_unpatched(self):
        with self.assertRaises(ValueError):
            patch_state(ceph().replace("!=", "=="))


if __name__ == "__main__":
    unittest.main()
