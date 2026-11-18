"""Pydantic contracts for tool inputs and search responses."""

from typing import Literal, Self, TypedDict

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


class SearchResultPayload(TypedDict):
    """JSON source shape exposed to ADK and Python callers."""

    title: str
    url: str
    snippet: str


class SearchResponsePayload(TypedDict):
    """Precisely typed serialized search response."""

    status: Literal["success", "no_results", "error"]
    query: str
    results: list[SearchResultPayload]
    message: str
    error_code: str


class ToolModel(BaseModel):
    """Reject unknown fields and accidental type coercion."""

    model_config = ConfigDict(strict=True, extra="forbid")


class WebSearchInput(ToolModel):
    """Validated search parameters before contacting the provider."""

    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=3, ge=1, le=10)
    region: str = Field(default="us-en", pattern=r"^[a-z]{2}-[a-z]{2}$")
    time_limit: Literal["", "d", "w", "m", "y"] = ""

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: object) -> object:
        if isinstance(value, str):
            return " ".join(value.split())
        return value


class SearchResult(ToolModel):
    """A validated source URL with bounded display text."""

    title: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    snippet: str = Field(max_length=1000)

    @field_validator("url")
    @classmethod
    def reject_credentials(cls, value: HttpUrl) -> HttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("Source URLs must not contain credentials.")
        return value


class SearchResponse(ToolModel):
    """The same JSON envelope for successful, empty, and failed searches."""

    status: Literal["success", "no_results", "error"]
    query: str = Field(max_length=500)
    results: list[SearchResult] = Field(default_factory=list, max_length=10)
    message: str = Field(min_length=1)
    error_code: str = ""

    def to_payload(self) -> SearchResponsePayload:
        """Serialize validated models with a precise, JSON-compatible type."""
        return {
            "status": self.status,
            "query": self.query,
            "results": [
                {
                    "title": result.title,
                    "url": str(result.url),
                    "snippet": result.snippet,
                }
                for result in self.results
            ],
            "message": self.message,
            "error_code": self.error_code,
        }

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status == "success":
            if not self.results or self.error_code:
                raise ValueError("Success requires results and no error code.")
        elif self.results:
            raise ValueError("Empty and error responses cannot contain results.")
        if (self.status == "error") != bool(self.error_code):
            raise ValueError("Only error responses require an error code.")
        return self


class CreateTaskInput(ToolModel):
    """Task fields accepted before any Notion request."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    due_date: str = ""
    priority: Literal["", "Low", "Medium", "High"] = ""

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, value: str) -> str:
        if value:
            import datetime

            if (
                len(value) != 10
                or datetime.date.fromisoformat(value).isoformat() != value
            ):
                raise ValueError("Use YYYY-MM-DD or an empty string for no due date.")
        return value


class CreatedTask(BaseModel):
    """Validate required fields in Notion's larger page response."""

    model_config = ConfigDict(strict=True, extra="ignore")
    id: str = Field(min_length=1)
    url: HttpUrl


class CreateTaskResponse(ToolModel):
    """Validated outcome; uncertain writes must not be retried blindly."""

    status: Literal["success", "error", "unknown"]
    message: str = Field(min_length=1)
    task_id: str = ""
    url: str = ""
    error_code: str = ""

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.status == "success":
            if not self.task_id or not self.url or self.error_code:
                raise ValueError(
                    "Success requires a task ID and URL, without an error."
                )
            HttpUrl(self.url)
        elif not self.error_code or self.task_id or self.url:
            raise ValueError(
                "Failed or uncertain outcomes require an error code without a task."
            )
        return self

    def to_payload(self) -> "CreateTaskPayload":
        return {
            "status": self.status,
            "message": self.message,
            "task_id": self.task_id,
            "url": self.url,
            "error_code": self.error_code,
        }


class CreateTaskPayload(TypedDict):
    """JSON-compatible task tool response."""

    status: Literal["success", "error", "unknown"]
    message: str
    task_id: str
    url: str
    error_code: str
