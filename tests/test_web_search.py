"""Search boundary checks without depending on external search services."""

import unittest
from unittest.mock import patch

from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException
from google.adk.tools import FunctionTool

from my_agent.tools import web_search


class WebSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_input_never_calls_provider(self):
        cases = [
            {"query": " "},
            {"query": "x" * 501},
            {"query": None},
            {"query": "python", "max_results": 0},
            {"query": "python", "max_results": True},
            {"query": "python", "max_results": 1.5},
            {"query": "python", "region": "invalid"},
            {"query": "python", "time_limit": "tomorrow"},
        ]
        with patch("my_agent.tools.DDGS") as provider:
            for kwargs in cases:
                with self.subTest(kwargs=kwargs):
                    result = await web_search(**kwargs)
                    self.assertEqual(result["status"], "error")
                    self.assertEqual(result["results"], [])
            provider.assert_not_called()

    async def test_normalizes_filters_deduplicates_and_limits(self):
        with patch("my_agent.tools.DDGS") as provider:
            provider.return_value.text.return_value = [
                {
                    "title": " Python  Docs ",
                    "href": "https://docs.python.org/3/#intro",
                    "body": "a " * 1000,
                },
                {"title": "duplicate", "href": "http://docs.python.org/3/#other"},
                {"href": "javascript:alert(1)"},
                {"href": "https://user:secret@example.com"},
                {"href": "https://[invalid"},
                None,
                {"url": "https://example.com", "snippet": " useful  example "},
                {"href": "https://extra.example.com"},
            ]
            result = await web_search("  python\n docs ", 2, "in-en", "w")
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["query"], "python docs")
            self.assertEqual(len(result["results"]), 2)
            self.assertEqual(result["results"][0]["title"], "Python Docs")
            self.assertLessEqual(len(result["results"][0]["snippet"]), 1000)
            self.assertEqual(result["results"][1]["snippet"], "useful example")
            provider.assert_called_once_with(timeout=8)
            provider.return_value.text.assert_called_once_with(
                "python docs",
                max_results=4,
                region="in-en",
                safesearch="moderate",
                timelimit="w",
                backend="auto",
            )

    async def test_empty_results(self):
        with patch("my_agent.tools.DDGS") as provider:
            provider.return_value.text.return_value = []
            self.assertEqual((await web_search("python"))["status"], "no_results")

    async def test_provider_failures_are_actionable_and_do_not_leak_details(self):
        for exc, code in [
            (TimeoutException, "TIMEOUT"),
            (RatelimitException, "RATE_LIMITED"),
            (DDGSException, "PROVIDER_ERROR"),
            (RuntimeError, "SEARCH_ERROR"),
        ]:
            with (
                self.subTest(code=code),
                patch("my_agent.tools.DDGS") as provider,
                patch("my_agent.tools.logger"),
            ):
                provider.return_value.text.side_effect = exc("private provider details")
                result = await web_search("python")
                self.assertEqual(result["error_code"], code)
                self.assertNotIn("private", result["message"])

    def test_adk_tool_schema(self):
        declaration = FunctionTool(func=web_search)._get_declaration()
        self.assertEqual(declaration.name, "web_search")
        self.assertIn("query", declaration.parameters_json_schema["properties"])


if __name__ == "__main__":
    unittest.main()
