import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from app.ai.base_provider import AIProviderError
from app.ai.openai_compatible import OpenAICompatibleProvider
from app.config import Settings
from app.utils.logging_config import redact_secrets


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._bytes = json.dumps(payload).encode("utf-8")

    def read(self, *_args):
        return self._bytes

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class AIProviderAndSettingsTests(unittest.TestCase):
    def test_rejects_empty_key_or_ssrf_url(self):
        with self.assertRaises(AIProviderError):
            OpenAICompatibleProvider("", "https://api.openai.com/v1", "gpt-4o-mini")
        with self.assertRaises(AIProviderError):
            OpenAICompatibleProvider("sk-test1234567890", "http://169.254.169.254/latest", "gpt-4o-mini")

    def test_parses_markdown_fenced_json_response(self):
        provider = OpenAICompatibleProvider(
            "sk-test1234567890", "https://api.openai.com/v1", "gpt-4o-mini", max_retries=0
        )
        payload = {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{"suggested_stem": "Annual_Tax_Return_2026", "subject": "Tax", "rationale": "Found 1040 form"}\n```'
                    }
                }
            ]
        }
        with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
            res = provider.suggest_name("scan.pdf", ".pdf", "Form 1040", "pdf")
            self.assertEqual(res["suggested_stem"], "Annual_Tax_Return_2026")
            self.assertEqual(res["subject"], "Tax")

    def test_retries_transient_429_then_succeeds(self):
        provider = OpenAICompatibleProvider(
            "sk-test1234567890",
            "https://api.openai.com/v1",
            "gpt-4o-mini",
            max_retries=2,
            retry_delay=0.01,
        )
        err_429 = urllib.error.HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=io.BytesIO(b'{"error": {"message": "Rate limit"}}'),
        )
        ok_payload = {
            "choices": [
                {
                    "message": {
                        "content": '{"suggested_stem": "Recovered_Name", "subject": "Test", "rationale": "OK"}'
                    }
                }
            ]
        }
        with patch(
            "urllib.request.urlopen",
            side_effect=[err_429, _FakeHTTPResponse(ok_payload)],
        ) as mocked:
            res = provider.suggest_name("a.txt", ".txt", "content", "text")
            self.assertEqual(res["suggested_stem"], "Recovered_Name")
            self.assertEqual(mocked.call_count, 2)

    def test_response_format_fallback_does_not_consume_retry_budget(self):
        """A 400 that rejects response_format must still be retried without it, even with no retries."""
        provider = OpenAICompatibleProvider(
            "sk-test1234567890", "https://api.openai.com/v1", "gpt-4o-mini", max_retries=0
        )
        err_400 = urllib.error.HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(b'{"error": {"message": "response_format is not supported"}}'),
        )
        ok_payload = {
            "choices": [
                {"message": {"content": '{"suggested_stem": "Plain_Mode_Name"}'}}
            ]
        }
        with patch(
            "urllib.request.urlopen",
            side_effect=[err_400, _FakeHTTPResponse(ok_payload)],
        ) as mocked:
            res = provider.suggest_name("a.txt", ".txt", "content", "text")
            self.assertEqual(res["suggested_stem"], "Plain_Mode_Name")
            self.assertEqual(mocked.call_count, 2)

    def test_does_not_retry_permanent_401(self):
        provider = OpenAICompatibleProvider(
            "sk-test1234567890",
            "https://api.openai.com/v1",
            "gpt-4o-mini",
            max_retries=2,
            retry_delay=0.01,
        )
        err_401 = urllib.error.HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"error": {"message": "Invalid key sk-secret12345678901234"}}'),
        )
        with patch("urllib.request.urlopen", side_effect=err_401) as mocked:
            with self.assertRaises(AIProviderError) as ctx:
                provider.suggest_name("a.txt", ".txt", "content", "text")
            self.assertEqual(mocked.call_count, 1)
            self.assertNotIn("sk-secret12345678901234", str(ctx.exception))

    def test_settings_validation_and_persistence_never_writes_api_key(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d) / "settings.json"
            s = Settings(
                api_key="sk-supersecretkey123456",
                max_filename_length=9999,
                naming_style="InvalidStyle",
                organize_by_category=True,
            )
            self.assertEqual(s.max_filename_length, 220)
            self.assertEqual(s.naming_style, "Underscore_Separated")

            import sys
            from unittest.mock import MagicMock

            fake_keyring = MagicMock()
            fake_keyring.get_password.return_value = "sk-supersecretkey123456"
            with patch.dict(sys.modules, {"keyring": fake_keyring}):
                s.save(config_path=cfg_path)
                fake_keyring.set_password.assert_called_once()
                raw_json = cfg_path.read_text(encoding="utf-8")
                self.assertNotIn("sk-supersecretkey123456", raw_json)
                self.assertNotIn("api_key", raw_json)

                loaded = Settings.load(config_path=cfg_path)
                self.assertEqual(loaded.api_key, "sk-supersecretkey123456")
                self.assertTrue(loaded.organize_by_category)

    def test_redact_secrets(self):
        raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and key sk-1234567890abcdef1234"
        cleaned = redact_secrets(raw)
        self.assertNotIn("eyJhbGciOi", cleaned)
        self.assertNotIn("sk-1234567890abcdef1234", cleaned)
        self.assertIn("[REDACTED]", cleaned)


if __name__ == "__main__":
    unittest.main()
