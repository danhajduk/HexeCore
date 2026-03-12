import unittest

from app.system.onboarding.provider_capability_normalization import normalize_provider_capability_report


class TestProviderCapabilityNormalization(unittest.TestCase):
    def test_normalizes_and_builds_unified_descriptors(self) -> None:
        providers, descriptors = normalize_provider_capability_report(
            [
                {
                    "provider": "OpenAI",
                    "available_models": [
                        {
                            "model_id": " GPT-4O-Mini ",
                            "pricing": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
                            "latency_metrics": {"p50_ms": 120},
                        }
                    ],
                },
                {
                    "provider": "openai",
                    "available_models": [{"model_id": "gpt-4o-mini", "pricing": {"input_per_1k": 0.0002}}],
                },
            ]
        )
        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0]["provider"], "openai")
        self.assertEqual(len(providers[0]["available_models"]), 1)
        self.assertEqual(providers[0]["available_models"][0]["normalized_model_id"], "gpt-4o-mini")
        self.assertEqual(len(descriptors), 1)
        self.assertEqual(descriptors[0]["normalized_model_id"], "gpt-4o-mini")
        self.assertEqual(descriptors[0]["provider_count"], 1)

    def test_rejects_invalid_provider_id(self) -> None:
        with self.assertRaises(ValueError):
            normalize_provider_capability_report([{"provider": "bad provider", "available_models": []}])


if __name__ == "__main__":
    unittest.main()
