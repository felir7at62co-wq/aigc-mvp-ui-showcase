import unittest

from core.llm_client import LLMClient


class LLMClientConfigTests(unittest.TestCase):
    def test_example_key_is_rejected_before_network_request(self):
        with self.assertRaisesRegex(ValueError, "未配置或仍是示例占位符"):
            LLMClient(
                "your_llm_api_key_here",
                "https://example.com/v1",
                "test-model",
                use_cache=False,
            )

    def test_empty_key_is_rejected_before_network_request(self):
        with self.assertRaisesRegex(ValueError, "未配置或仍是示例占位符"):
            LLMClient("", "https://example.com/v1", "test-model", use_cache=False)
