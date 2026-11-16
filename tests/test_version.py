"""Version identification for the status dashboard (SYSTEM.md §13).

The release manifest lives in the repo (release.json); the deploy job
generates the public version.json from it. The footer never hardcodes
a version string: it fetches /version.json at runtime and shows nothing
when that fetch fails.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"\d+\.\d+\.\d+")


class ReleaseManifestTests(unittest.TestCase):
    def test_release_json_is_valid_semver_without_self_sha(self):
        manifest = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["site"], "status")
        self.assertRegex(manifest["version"], SEMVER)
        self.assertRegex(manifest["chiSystemVersion"], SEMVER)
        # A manifest must never contain its own commit SHA: the SHA only
        # exists after the commit is created, so it cannot be part of it.
        for forbidden in ("commit", "commitShort", "deployedAt"):
            self.assertNotIn(forbidden, manifest)

    def test_footers_read_version_at_runtime_and_do_not_hardcode_it(self):
        manifest = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))
        version = manifest["version"]
        for page in ("index.html", "action/index.html", "actions/index.html"):
            html = (ROOT / page).read_text(encoding="utf-8")
            self.assertIn("data-version", html, page)
            self.assertNotIn("v" + version, html, page)
            self.assertNotIn(version, html, page)


if __name__ == "__main__":
    unittest.main()
