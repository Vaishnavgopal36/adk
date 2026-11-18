"""Validation boundaries and ADK compatibility for tool contracts."""

import unittest

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from pydantic import HttpUrl, ValidationError

from my_agent.agent import root_agent
from my_agent.schema import SearchResponse, SearchResult, WebSearchInput
from my_agent.tools import create_task, web_search


class SchemaTests(unittest.TestCase):
    def test_search_input_rejects_coercion_and_extra_fields(self):
        for kwargs in [
            {"query": "python", "max_results": "3"},
            {"query": "python", "max_results": True},
            {"query": "python", "unexpected": "value"},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                WebSearchInput.model_validate(kwargs)
        self.assertEqual(WebSearchInput(query="  Python\n docs ").query, "Python docs")

    def test_source_url_and_text_constraints(self):
        for url in [
            "javascript:alert(1)",
            "not a URL",
            "https://user:secret@example.com",
        ]:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                SearchResult.model_validate(
                    {"title": "Title", "url": url, "snippet": ""}
                )
        with self.assertRaises(ValidationError):
            SearchResult(title="", url=HttpUrl("https://example.com"), snippet="")
        source = SearchResult(
            title="Title", url=HttpUrl("https://example.com/page"), snippet="Text"
        )
        self.assertIsInstance(source.model_dump(mode="json")["url"], str)

    def test_response_status_contract(self):
        source = SearchResult(
            title="Title", url=HttpUrl("https://example.com"), snippet=""
        )
        invalid = [
            {"status": "success"},
            {"status": "no_results", "results": [source]},
            {"status": "error"},
            {"status": "no_results", "error_code": "TIMEOUT"},
            {"status": "success", "results": [source], "error_code": "TIMEOUT"},
        ]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                SearchResponse(query="python", message="Explanation", **kwargs)
        SearchResponse(
            status="success", query="python", message="Found", results=[source]
        )
        SearchResponse(status="no_results", query="python", message="Try broader terms")
        SearchResponse(
            status="error", query="python", message="Try later", error_code="TIMEOUT"
        )

    def test_adk_registration_still_uses_primitive_arguments(self):
        declaration = FunctionTool(func=web_search)._get_declaration()
        assert declaration is not None
        schema = declaration.parameters_json_schema
        assert schema is not None
        self.assertTrue(schema["properties"])
        for agent in root_agent.sub_agents:
            assert isinstance(agent, Agent)
            self.assertEqual(agent.tools, [web_search, create_task])


if __name__ == "__main__":
    unittest.main()
