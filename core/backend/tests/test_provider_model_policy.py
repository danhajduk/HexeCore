import tempfile
import unittest
from pathlib import Path

from app.system.onboarding.provider_model_policy import ProviderModelApprovalPolicyService, ProviderModelPolicyStore


class TestProviderModelPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = ProviderModelPolicyStore(path=Path(self.tmpdir.name) / "provider_model_policy.json")
        self.service = ProviderModelApprovalPolicyService(self.store)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_allowlist_roundtrip(self) -> None:
        updated = self.service.set_allowlist(
            provider="openai",
            allowed_models=["gpt-4o-mini", "gpt-4.1-mini"],
            updated_by="admin",
        )
        self.assertEqual(updated.provider, "openai")
        self.assertEqual(updated.allowed_models, ["gpt-4.1-mini", "gpt-4o-mini"])

        reloaded = ProviderModelPolicyStore(path=Path(self.tmpdir.name) / "provider_model_policy.json")
        again = ProviderModelApprovalPolicyService(reloaded)
        self.assertTrue(again.has_explicit_policy("openai"))
        self.assertTrue(again.is_model_allowed(provider="openai", model_id="gpt-4o-mini"))
        self.assertFalse(again.is_model_allowed(provider="openai", model_id="gpt-5"))

    def test_provider_without_policy_allows_all_models(self) -> None:
        self.assertFalse(self.service.has_explicit_policy("openai"))
        self.assertTrue(self.service.is_model_allowed(provider="openai", model_id="gpt-5"))


if __name__ == "__main__":
    unittest.main()
