from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "validate_hexe_branding.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_hexe_branding", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Hexe branding validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class HexeBrandingValidationTests(unittest.TestCase):
    def test_current_repo_has_no_unapproved_synthia_references(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_allowlist_entries_are_reasoned(self) -> None:
        validator = load_validator()

        self.assertTrue(validator.ALLOWED_LEGACY_REFERENCES)
        for reference in validator.ALLOWED_LEGACY_REFERENCES:
            self.assertTrue(reference.reason.strip())

    def test_rejects_unqualified_synthia_branding(self) -> None:
        validator = load_validator()

        self.assertIsNone(
            validator.allow_match("frontend/src/App.tsx", 'const title = "Synthia Dashboard";')
        )

    def test_accepts_documented_legacy_env_alias(self) -> None:
        validator = load_validator()

        self.assertIsNotNone(
            validator.allow_match("backend/app/core/env.py", 'LEGACY_ENV_PREFIX = "SYNTHIA_"')
        )


if __name__ == "__main__":
    unittest.main()
