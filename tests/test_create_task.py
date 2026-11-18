"""Notion task validation and HTTP integration without real writes."""

import json
import unittest
from unittest.mock import patch

import httpx
from google.adk.tools import FunctionTool
from pydantic import ValidationError

from my_agent.schema import CreateTaskInput
from my_agent.tools import create_task

TASK_ENV = {
    "NOTION_API_KEY": "test_token",
    "NOTION_DATA_SOURCE_ID": "12345678-1234-1234-1234-123456789abc",
    "NOTION_TITLE_PROPERTY": "Task name",
    "NOTION_DUE_PROPERTY": "Due",
    "NOTION_PRIORITY_PROPERTY": "Importance",
}


class CreateTaskTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_credentials_does_not_send_request(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("my_agent.tools.httpx.AsyncClient") as client,
        ):
            result = await create_task("Learn sorting")
            self.assertEqual(result["error_code"], "NOT_CONFIGURED")
            client.assert_not_called()

    async def test_placeholder_config_does_not_send_request(self):
        for token, source in [
            (
                "replace_with_notion_integration_token",
                TASK_ENV["NOTION_DATA_SOURCE_ID"],
            ),
            ("test_token", "replace_with_notion_data_source_uuid"),
        ]:
            with (
                patch.dict(
                    "os.environ",
                    {"NOTION_API_KEY": token, "NOTION_DATA_SOURCE_ID": source},
                    clear=True,
                ),
                patch("my_agent.tools.httpx.AsyncClient") as client,
            ):
                self.assertEqual(
                    (await create_task("Test"))["error_code"], "NOT_CONFIGURED"
                )
                client.assert_not_called()

    async def test_invalid_task_does_not_send_request(self):
        for kwargs in [
            {"title": " "},
            {"title": "x" * 201},
            {"title": "Test", "description": "x" * 2001},
            {"title": "Test", "due_date": "2026-02-30"},
            {"title": "Test", "due_date": "tomorrow"},
            {"title": "Test", "priority": "urgent"},
        ]:
            with (
                self.subTest(kwargs=kwargs),
                patch("my_agent.tools.httpx.AsyncClient") as client,
            ):
                result = await create_task(**kwargs)
                self.assertEqual(result["error_code"], "INVALID_TASK")
                client.assert_not_called()

    async def test_success_uses_property_mapping_and_page_body(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "id": "created-page",
                    "url": "https://www.notion.so/created-page",
                    "object": "page",
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with (
            patch.dict("os.environ", TASK_ENV, clear=True),
            patch("my_agent.tools.httpx.AsyncClient", return_value=client),
        ):
            result = await create_task(
                "  Learn  sorting ", "Practice insertion sort", "2026-11-20", "High"
            )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["task_id"], "created-page")
        self.assertTrue(result["url"].startswith("https://www.notion.so/"))
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request.headers["Authorization"], "Bearer test_token")
        self.assertEqual(request.headers["Notion-Version"], "2025-09-03")
        payload = json.loads(request.content)
        self.assertEqual(
            payload["parent"]["data_source_id"], TASK_ENV["NOTION_DATA_SOURCE_ID"]
        )
        self.assertEqual(
            payload["properties"]["Task name"]["title"][0]["text"]["content"],
            "Learn sorting",
        )
        self.assertEqual(payload["properties"]["Due"]["date"]["start"], "2026-11-20")
        self.assertEqual(payload["properties"]["Importance"]["select"]["name"], "High")
        self.assertEqual(
            payload["children"][0]["paragraph"]["rich_text"][0]["text"]["content"],
            "Practice insertion sort",
        )

    async def test_errors_and_uncertain_writes_are_not_retried(self):
        for status, expected, outcome in [
            (401, "NOTION_ACCESS_ERROR", "error"),
            (403, "NOTION_ACCESS_ERROR", "error"),
            (404, "NOTION_ACCESS_ERROR", "error"),
            (400, "NOTION_REQUEST_ERROR", "error"),
            (429, "RATE_LIMITED", "error"),
            (529, "RATE_LIMITED", "error"),
            (503, "WRITE_UNCONFIRMED", "unknown"),
            (200, "WRITE_UNCONFIRMED", "unknown"),
        ]:
            requests: list[httpx.Request] = []

            def handler(
                request: httpx.Request,
                captured: list[httpx.Request] = requests,
                response_status: int = status,
            ) -> httpx.Response:
                captured.append(request)
                return httpx.Response(
                    response_status, json={"message": "private details"}
                )

            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            with (
                self.subTest(status=status),
                patch.dict("os.environ", TASK_ENV, clear=True),
                patch("my_agent.tools.httpx.AsyncClient", return_value=client),
            ):
                result = await create_task("Test")
            self.assertEqual(result["status"], outcome)
            self.assertEqual(result["error_code"], expected)
            self.assertEqual(result["url"], "")
            self.assertEqual(len(requests), 1)
            payload = json.loads(requests[0].content)
            self.assertNotIn("children", payload)
            self.assertEqual(list(payload["properties"]), ["Task name"])
            self.assertNotIn("private", result["message"])

    async def test_timeout_is_uncertain(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("private details", request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with (
            patch.dict("os.environ", TASK_ENV, clear=True),
            patch("my_agent.tools.httpx.AsyncClient", return_value=client),
        ):
            result = await create_task("Test")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["error_code"], "WRITE_UNCONFIRMED")

    def test_adk_schema_has_no_credentials(self):
        declaration = FunctionTool(func=create_task)._get_declaration()
        assert declaration is not None
        schema = declaration.parameters_json_schema
        assert schema is not None
        self.assertEqual(
            set(schema["properties"]), {"title", "description", "due_date", "priority"}
        )
        self.assertEqual(schema["required"], ["title"])
        with self.assertRaises(ValidationError):
            CreateTaskInput.model_validate({"title": "Test", "extra": True})
