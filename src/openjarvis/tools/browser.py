"""Browser automation tools — Playwright-based web interaction."""

from __future__ import annotations

import base64
import queue
import threading
from concurrent.futures import Future
from typing import Any, Callable

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


class _BrowserSession:
    """Manages a shared Playwright browser session (lazy init).

    Playwright's sync API is thread-affine: a browser/page must be driven
    from the same OS thread that created it. ``ToolExecutor`` dispatches
    each tool call on a fresh short-lived thread, so touching ``page``
    directly from the caller's thread breaks on the second call ("cannot
    switch to a different thread"). Instead, all Playwright interaction is
    routed through one persistent worker thread owned by this session via
    :meth:`run`.
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._page = None
        self._thread: threading.Thread | None = None
        self._queue: "queue.Queue[tuple[Callable[[Any], Any], Future] | None]" = (
            queue.Queue()
        )

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            fn, future = item
            try:
                future.set_result(fn(self._ensure_page()))
            except BaseException as exc:  # noqa: BLE001 - propagate to caller
                future.set_exception(exc)

    def _ensure_page(self):
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "playwright not installed. Install with: uv sync --extra browser"
            )
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._page = self._browser.new_page()
        return self._page

    def run(self, fn: Callable[[Any], Any]) -> Any:
        """Run ``fn(page)`` on this session's dedicated browser thread and
        block for the result, re-raising any exception in the caller."""
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()
        future: Future = Future()
        self._queue.put((fn, future))
        return future.result()

    def close(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            def _shutdown(_page: Any) -> None:
                if self._browser:
                    self._browser.close()
                if self._playwright:
                    self._playwright.stop()

            try:
                self.run(_shutdown)
            except Exception:
                pass
            self._queue.put(None)
        self._playwright = self._browser = self._page = None


_session = _BrowserSession()


# ---------------------------------------------------------------------------
# Tool 1: BrowserNavigateTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("browser_navigate")
class BrowserNavigateTool(BaseTool):
    """Navigate to a URL in the browser."""

    tool_id = "browser_navigate"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="browser_navigate",
            description=(
                "Navigate to a URL in the browser."
                " Returns the page title and text content."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to navigate to.",
                    },
                    "wait_for": {
                        "type": "string",
                        "description": (
                            "Wait condition: 'load', 'domcontentloaded',"
                            " or 'networkidle'. Default: 'load'."
                        ),
                    },
                },
                "required": ["url"],
            },
            category="browser",
            required_capabilities=["network:fetch"],
        )

    def execute(self, **params: Any) -> ToolResult:
        url = params.get("url", "")
        if not url:
            return ToolResult(
                tool_name="browser_navigate",
                content="No URL provided.",
                success=False,
            )

        wait_for = params.get("wait_for", "load")
        if wait_for not in ("load", "domcontentloaded", "networkidle"):
            wait_for = "load"

        # SSRF check — never skipped. check_ssrf falls back to a pure-Python
        # implementation when the Rust backend is unavailable, so an
        # uncompiled extension must not silently disable SSRF protection.
        from openjarvis.security.ssrf import check_ssrf

        ssrf_error = check_ssrf(url)
        if ssrf_error:
            return ToolResult(
                tool_name="browser_navigate",
                content=f"SSRF blocked: {ssrf_error}",
                success=False,
            )

        try:
            def _do(page: Any) -> tuple[Any, str, str]:
                response = page.goto(url, wait_until=wait_for)
                return response, page.title(), page.inner_text("body")

            response, title, text_content = _session.run(_do)
            if len(text_content) > 5000:
                text_content = text_content[:5000] + "\n\n[Content truncated]"

            status = response.status if response else None
            return ToolResult(
                tool_name="browser_navigate",
                content=f"Title: {title}\n\n{text_content}",
                success=True,
                metadata={"url": url, "title": title, "status": status},
            )
        except ImportError:
            return ToolResult(
                tool_name="browser_navigate",
                content=(
                    "playwright not installed. Install with: uv sync --extra browser"
                ),
                success=False,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="browser_navigate",
                content=f"Navigation error: {exc}",
                success=False,
            )


# ---------------------------------------------------------------------------
# Tool 2: BrowserClickTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("browser_click")
class BrowserClickTool(BaseTool):
    """Click an element on the page."""

    tool_id = "browser_click"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="browser_click",
            description=(
                "Click an element on the current page."
                " Use a CSS selector or text content to identify the element."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector or text content of the element.",
                    },
                    "by_text": {
                        "type": "boolean",
                        "description": (
                            "If true, click by text content"
                            " instead of CSS selector. Default: false."
                        ),
                    },
                },
                "required": ["selector"],
            },
            category="browser",
        )

    def execute(self, **params: Any) -> ToolResult:
        selector = params.get("selector", "")
        if not selector:
            return ToolResult(
                tool_name="browser_click",
                content="No selector provided.",
                success=False,
            )

        by_text = params.get("by_text", False)

        try:
            def _do(page: Any) -> None:
                if by_text:
                    page.get_by_text(selector).click()
                else:
                    page.click(selector)

            _session.run(_do)

            return ToolResult(
                tool_name="browser_click",
                content=f"Clicked element: {selector}",
                success=True,
                metadata={"selector": selector, "by_text": by_text},
            )
        except ImportError:
            return ToolResult(
                tool_name="browser_click",
                content=(
                    "playwright not installed. Install with: uv sync --extra browser"
                ),
                success=False,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="browser_click",
                content=f"Click error: {exc}",
                success=False,
            )


# ---------------------------------------------------------------------------
# Tool 3: BrowserTypeTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("browser_type")
class BrowserTypeTool(BaseTool):
    """Type text into a form field."""

    tool_id = "browser_type"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="browser_type",
            description=(
                "Type text into a form field on the current page."
                " Can clear the field first or append to existing content."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector of the input field.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type into the field.",
                    },
                    "clear": {
                        "type": "boolean",
                        "description": (
                            "If true, clear the field before typing. Default: true."
                        ),
                    },
                },
                "required": ["selector", "text"],
            },
            category="browser",
        )

    def execute(self, **params: Any) -> ToolResult:
        selector = params.get("selector", "")
        text = params.get("text", "")

        if not selector:
            return ToolResult(
                tool_name="browser_type",
                content="No selector provided.",
                success=False,
            )
        if not text:
            return ToolResult(
                tool_name="browser_type",
                content="No text provided.",
                success=False,
            )

        clear = params.get("clear", True)

        try:
            def _do(page: Any) -> None:
                if clear:
                    page.fill(selector, text)
                else:
                    page.type(selector, text)

            _session.run(_do)

            return ToolResult(
                tool_name="browser_type",
                content=f"Typed text into: {selector}",
                success=True,
                metadata={"selector": selector},
            )
        except ImportError:
            return ToolResult(
                tool_name="browser_type",
                content=(
                    "playwright not installed. Install with: uv sync --extra browser"
                ),
                success=False,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="browser_type",
                content=f"Type error: {exc}",
                success=False,
            )


# ---------------------------------------------------------------------------
# Tool 4: BrowserScreenshotTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("browser_screenshot")
class BrowserScreenshotTool(BaseTool):
    """Take a screenshot of the current page."""

    tool_id = "browser_screenshot"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="browser_screenshot",
            description=(
                "Take a screenshot of the current browser page."
                " Returns the screenshot as base64-encoded data."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Optional file path to save the screenshot.",
                    },
                    "full_page": {
                        "type": "boolean",
                        "description": (
                            "If true, capture the full scrollable page. Default: false."
                        ),
                    },
                },
            },
            category="browser",
        )

    def execute(self, **params: Any) -> ToolResult:
        path = params.get("path")
        full_page = params.get("full_page", False)

        try:
            screenshot_bytes = _session.run(
                lambda page: page.screenshot(full_page=full_page)
            )

            if path:
                with open(path, "wb") as f:
                    f.write(screenshot_bytes)

            b64_data = base64.b64encode(screenshot_bytes).decode("utf-8")

            description = "Screenshot taken"
            if full_page:
                description += " (full page)"
            if path:
                description += f", saved to {path}"

            return ToolResult(
                tool_name="browser_screenshot",
                content=description,
                success=True,
                metadata={"screenshot_base64": b64_data},
            )
        except ImportError:
            return ToolResult(
                tool_name="browser_screenshot",
                content=(
                    "playwright not installed. Install with: uv sync --extra browser"
                ),
                success=False,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="browser_screenshot",
                content=f"Screenshot error: {exc}",
                success=False,
            )


# ---------------------------------------------------------------------------
# Tool 5: BrowserExtractTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("browser_extract")
class BrowserExtractTool(BaseTool):
    """Extract content from the current page."""

    tool_id = "browser_extract"
    is_local = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="browser_extract",
            description=(
                "Extract content from the current browser page."
                " Supports extracting text, links, or tables."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": (
                            "CSS selector to extract from. Default: 'body'."
                        ),
                    },
                    "extract_type": {
                        "type": "string",
                        "description": (
                            "Type of extraction: 'text', 'links',"
                            " or 'tables'. Default: 'text'."
                        ),
                    },
                },
            },
            category="browser",
        )

    def execute(self, **params: Any) -> ToolResult:
        selector = params.get("selector", "body")
        extract_type = params.get("extract_type", "text")

        if extract_type not in ("text", "links", "tables"):
            return ToolResult(
                tool_name="browser_extract",
                content=(
                    f"Invalid extract_type: '{extract_type}'."
                    " Must be 'text', 'links', or 'tables'."
                ),
                success=False,
            )

        try:
            def _do(page: Any) -> Any:
                if extract_type == "text":
                    return page.inner_text(selector)
                if extract_type == "links":
                    return page.eval_on_selector_all(
                        f"{selector} a[href]",
                        """elements => elements.map(el => ({
                            href: el.href,
                            text: el.innerText.trim()
                        }))""",
                    )
                return page.eval_on_selector_all(
                    f"{selector} table",
                    """elements => elements.map(el => el.innerText)""",
                )

            raw = _session.run(_do)

            if extract_type == "text":
                content = raw
                if len(content) > 10000:
                    content = content[:10000] + "\n\n[Content truncated]"
                return ToolResult(
                    tool_name="browser_extract",
                    content=content,
                    success=True,
                    metadata={"selector": selector, "extract_type": extract_type},
                )

            elif extract_type == "links":
                links = raw
                lines = []
                for link in links:
                    text = link.get("text", "")
                    href = link.get("href", "")
                    lines.append(f"- [{text}]({href})")
                content = "\n".join(lines) if lines else "No links found."
                if len(content) > 10000:
                    content = content[:10000] + "\n\n[Content truncated]"
                return ToolResult(
                    tool_name="browser_extract",
                    content=content,
                    success=True,
                    metadata={
                        "selector": selector,
                        "extract_type": extract_type,
                        "num_links": len(links),
                    },
                )

            else:  # tables
                tables_text = raw
                if tables_text:
                    content = "\n\n---\n\n".join(tables_text)
                else:
                    content = "No tables found."
                if len(content) > 10000:
                    content = content[:10000] + "\n\n[Content truncated]"
                return ToolResult(
                    tool_name="browser_extract",
                    content=content,
                    success=True,
                    metadata={
                        "selector": selector,
                        "extract_type": extract_type,
                        "num_tables": len(tables_text),
                    },
                )

        except ImportError:
            return ToolResult(
                tool_name="browser_extract",
                content=(
                    "playwright not installed. Install with: uv sync --extra browser"
                ),
                success=False,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="browser_extract",
                content=f"Extract error: {exc}",
                success=False,
            )


__all__ = [
    "BrowserNavigateTool",
    "BrowserClickTool",
    "BrowserTypeTool",
    "BrowserScreenshotTool",
    "BrowserExtractTool",
]
