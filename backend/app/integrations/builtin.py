import logging
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import re

import httpx
from pydantic import BaseModel, Field
from readability import Document
from markdownify import markdownify as md

logger = logging.getLogger("ocin")


class HttpResult(BaseModel):
    """Result from http_fetch tool."""
    status_code: int
    body: str
    headers: dict[str, str] = Field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.model_dump()


class DateTimeResult(BaseModel):
    """Result from get_datetime tool."""
    date: str
    time: str
    day_of_week: str
    unix_timestamp: int
    timezone: str

    def to_dict(self) -> dict:
        return self.model_dump()


class SearchResult(BaseModel):
    """Single search result from web_search tool."""
    title: str
    url: str
    snippet: str


class WebSearchResult(BaseModel):
    """Result from web_search tool."""
    results: list[SearchResult]
    query: str
    total_results: int

    def to_dict(self) -> dict:
        return self.model_dump()


class WebFetchResult(BaseModel):
    """Result from web_fetch tool."""
    url: str
    status: int
    content_markdown: str
    content_length: int

    def to_dict(self) -> dict:
        return self.model_dump()


async def http_fetch(
    url: str,
    method: str = "GET",
    body: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 15.0,
) -> HttpResult:
    """
    Make an HTTP request to a URL.

    Args:
        url: The URL to fetch
        method: HTTP method (GET, POST, etc.)
        body: Request body (for POST, PUT, etc.)
        headers: Request headers
        timeout: Request timeout in seconds

    Returns:
        HttpResult with status code, body (truncated to 10k chars), and headers
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                content=body,
                headers=headers,
            )

            # Truncate body to 10k characters
            body_text = response.text
            if len(body_text) > 10000:
                body_text = body_text[:10000] + "... [truncated]"

            return HttpResult(
                status_code=response.status_code,
                body=body_text,
                headers=dict(response.headers),
            )
    except Exception as e:
        logger.error({"event": "http_fetch", "url": url, "error": str(e)})
        raise ValueError(f"HTTP request failed: {str(e)}")


def get_datetime(timezone: str = "UTC") -> DateTimeResult:
    """
    Get the current date and time.

    Args:
        timezone: IANA timezone identifier (e.g., "America/New_York", "UTC")

    Returns:
        DateTimeResult with date, time, day of week, unix timestamp, and timezone
    """
    try:
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)

        return DateTimeResult(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M:%S"),
            day_of_week=now.strftime("%A"),
            unix_timestamp=int(now.timestamp()),
            timezone=timezone,
        )
    except Exception as e:
        logger.error({"event": "get_datetime", "timezone": timezone, "error": str(e)})
        # Fallback to UTC
        return get_datetime("UTC")


async def request_approval(
    kind: str,
    title: str,
    description: str,
    payload: dict = None,
) -> dict:
    """
    Request user approval for an agent action.

    When called by an agent, this tool pauses execution and requests
    user confirmation before proceeding. Used for:
    - Sending emails
    - Posting to social media
    - Creating resources that cost money
    - Any action user wants to review before execution

    Args:
        kind: Type of approval (send_email, post_social, execute_action)
        title: Short user-facing summary
        description: Longer explanation
        payload: Full payload agent wants to execute

    Returns:
        Dict with approval details that signals to agent runner to pause

    Behavior:
        1. Returns a special response that agent runner detects
        2. The agent runner will catch this and pause execution
        3. User can then approve/reject via approvals API
        4. If approved, a new child run continues execution
    """
    # Import here to avoid circular dependency
    from app.core.exceptions import ApprovalRequestedException

    # Return a special response that signals to agent runner to pause
    # The agent_runner will create the actual Approval record
    approval_id = str(uuid.uuid4())

    logger.info({
        "event": "approval_request_created",
        "approval_id": approval_id,
        "kind": kind,
        "title": title,
        "description": description,
    })

    # Return response that triggers pause in agent_runner
    # The agent_runner will create an actual Approval record
    return {
        "_approval_request": {
            "approval_id": approval_id,
            "kind": kind,
            "title": title,
            "description": description,
            "payload": payload,
        }
    }


async def web_search(
    query: str,
    max_results: int = 5,
    api_key: str = None,
    timeout: float = 15.0,
) -> WebSearchResult:
    """
    Search the web using Tavily API.

    Args:
        query: Search query string
        max_results: Maximum number of results (default 5, capped at 10)
        api_key: Tavily API key (injected at runtime)
        timeout: Request timeout in seconds

    Returns:
        WebSearchResult with list of search results (title, url, snippet)

    Raises:
        ValueError: If API key is missing or request fails
    """
    if not api_key:
        raise ValueError("Tavily API key is required for web search. Please add your Tavily key in Settings.")

    # Cap max_results at 10
    max_results = min(max_results, 10)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
                headers={"Content-Type": "application/json"},
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error({
                    "event": "web_search_failed",
                    "query": query,
                    "status_code": response.status_code,
                    "error": error_text,
                })
                raise ValueError(f"Tavily API error: {response.status_code} - {error_text}")

            data = response.json()

            # Extract results from Tavily response
            tavily_results = data.get("results", [])

            # Build search results with truncated snippets
            search_results = []
            for item in tavily_results[:max_results]:
                snippet = item.get("content", "")
                # Truncate snippet to 500 characters
                if len(snippet) > 500:
                    snippet = snippet[:500] + "..."

                search_results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=snippet,
                    )
                )

            logger.info({
                "event": "web_search_success",
                "query": query,
                "results_count": len(search_results),
            })

            return WebSearchResult(
                results=search_results,
                query=query,
                total_results=len(search_results),
            )

    except httpx.TimeoutException:
        logger.error({"event": "web_search_timeout", "query": query})
        raise ValueError(f"Web search timed out after {timeout} seconds")
    except Exception as e:
        logger.error({"event": "web_search_error", "query": query, "error": str(e)})
        raise ValueError(f"Web search failed: {str(e)}")


async def web_fetch(
    url: str,
    timeout: float = 15.0,
    max_content_length: int = 200_000,
) -> WebFetchResult:
    """
    Fetch a URL and convert HTML to markdown.

    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds
        max_content_length: Maximum response body size in bytes

    Returns:
        WebFetchResult with url, status, and markdown content

    Raises:
        ValueError: If URL is invalid or request fails
    """
    # Basic URL validation
    if not url or not re.match(r'^https?://', url):
        raise ValueError("Invalid URL. Must start with http:// or https://")

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)

            # Check content type
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type.lower():
                logger.warning({
                    "event": "web_fetch_non_html",
                    "url": url,
                    "content_type": content_type,
                })
                raise ValueError(f"URL does not return HTML content (got {content_type})")

            # Check content length
            content_length = len(response.content)
            if content_length > max_content_length:
                logger.warning({
                    "event": "web_fetch_too_large",
                    "url": url,
                    "content_length": content_length,
                    "max_length": max_content_length,
                })
                raise ValueError(
                    f"Response too large ({content_length} bytes, max {max_content_length})"
                )

            # Convert HTML to markdown
            html_content = response.text
            try:
                # Use readability for better content extraction
                doc = Document(html_content)
                cleaned_html = doc.summary()
                markdown_content = md(cleaned_html)
            except Exception as e:
                # Fallback: convert raw HTML to markdown
                logger.warning({
                    "event": "readability_fallback",
                    "url": url,
                    "error": str(e),
                })
                markdown_content = md(html_content)

            # Truncate if needed (markdown conversion can be verbose)
            if len(markdown_content) > 50000:
                markdown_content = markdown_content[:50000] + "\n\n... [content truncated]"

            logger.info({
                "event": "web_fetch_success",
                "url": url,
                "status_code": response.status_code,
                "content_length": len(markdown_content),
            })

            return WebFetchResult(
                url=url,
                status=response.status_code,
                content_markdown=markdown_content,
                content_length=len(markdown_content),
            )

    except httpx.TimeoutException:
        logger.error({"event": "web_fetch_timeout", "url": url})
        raise ValueError(f"Web fetch timed out after {timeout} seconds")
    except Exception as e:
        logger.error({"event": "web_fetch_error", "url": url, "error": str(e)})
        raise ValueError(f"Web fetch failed: {str(e)}")
