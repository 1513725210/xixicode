"""Web 工具 — web_fetch + web_search。

参考 MiniCode web-fetch.ts 和 web-search.ts：
  web_fetch:  通过 httpx 获取网页并提取可读文本
  web_search: 通过 DuckDuckGo Lite 搜索网页
"""

import re
from html.parser import HTMLParser

import httpx

from minicode.tool.base import Tool, ToolResult


# ── HTML 文本提取器 ──


class _TextExtractor(HTMLParser):
    """从 HTML 中提取纯文本（去除标签和脚本）。"""

    def __init__(self):
        super().__init__()
        self.text: list[str] = []
        self._skip_tags: set[str] = {"script", "style", "noscript", "iframe", "svg"}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self.text.append("")  # 占位

    def handle_data(self, data):
        stripped = data.strip()
        if stripped:
            self.text.append(stripped)

    def get_text(self) -> str:
        return "\n".join(self.text)


def _extract_text_from_html(html: str) -> str:
    """从 HTML 字符串中提取纯文本。"""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.get_text()


# ── web_fetch ──


class WebFetch(Tool):
    """获取网页内容并提取可读文本。

    参考 MiniCode web-fetch.ts：
    - HTTP/HTTPS URL
    - 返回 TITLE + 纯文本内容
    - 支持 max_chars 截断
    """

    name = "web_fetch"
    description = (
        "获取网页内容并提取可读文本。搭配 web_search 使用，"
        "在搜索后获取具体页面的完整内容。"
    )
    parameters = {
        "url": "要获取的 HTTP/HTTPS URL",
        "max_chars": "最大返回字符数（默认 12000）",
    }
    risk_level = "safe"

    MAX_DEFAULT = 12000
    TIMEOUT_SEC = 15.0

    async def execute(self, url: str, max_chars: int = 0) -> ToolResult:
        """获取网页。

        Args:
            url: HTTP/HTTPS URL
            max_chars: 最大返回字符数，默认 12000

        Returns:
            ToolResult
        """
        if not url.startswith(("http://", "https://")):
            return ToolResult(ok=False, output="", error=f"仅支持 HTTP/HTTPS URL: {url}")

        max_chars = max_chars or self.MAX_DEFAULT

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SEC) as client:
                resp = await client.get(url, follow_redirects=True)
        except httpx.TimeoutException:
            return ToolResult(ok=False, output="", error=f"请求超时: {url}")
        except httpx.RequestError as exc:
            return ToolResult(ok=False, output="", error=f"请求失败: {url} ({exc})")

        if resp.status_code >= 400:
            return ToolResult(
                ok=False, output="",
                error=f"HTTP {resp.status_code}: {url}",
            )

        content_type = resp.headers.get("content-type", "")
        html = resp.text

        # 提取标题
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # 提取正文
        if "text/html" in content_type:
            text = _extract_text_from_html(html)
        else:
            text = html

        # 截断
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... (内容截断，原 {len(text)} 字符)"

        lines = [
            f"URL: {str(resp.url)}",
            f"STATUS: {resp.status_code}",
            f"CONTENT_TYPE: {content_type}",
        ]
        if title:
            lines.append(f"TITLE: {title}")
        lines.append("")
        lines.append(text)

        return ToolResult(
            ok=True,
            output="\n".join(lines),
            artifacts=[{
                "url": str(resp.url),
                "status": resp.status_code,
                "chars": len(text),
            }],
        )


# ── web_search ──


class WebSearch(Tool):
    """搜索网页（DuckDuckGo Lite）。

    参考 MiniCode web-search.ts：
    - 通过 DDG Lite 获取搜索结果
    - 返回标题 + URL + 摘要
    - 支持域名白名单/黑名单
    """

    name = "web_search"
    description = (
        "通过 DuckDuckGo 搜索网页。用于获取最新信息、文档或代码库外知识。"
    )
    parameters = {
        "query": "搜索关键词",
        "max_results": "最大返回数（默认 5，上限 20）",
        "allowed_domains": "仅返回这些域名的结果（列表）",
        "blocked_domains": "排除这些域名的结果（列表）",
    }
    risk_level = "safe"

    DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
    TIMEOUT_SEC = 10.0

    async def execute(
        self,
        query: str,
        max_results: int = 5,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
    ) -> ToolResult:
        """搜索网页。

        Args:
            query: 搜索关键词
            max_results: 最大返回数
            allowed_domains: 白名单域名
            blocked_domains: 黑名单域名

        Returns:
            ToolResult
        """
        if not query or not query.strip():
            return ToolResult(ok=False, output="", error="搜索关键词不能为空")

        max_results = max(1, min(max_results, 20))

        # 互斥检查
        if allowed_domains and blocked_domains:
            return ToolResult(
                ok=False, output="",
                error="不能同时指定 allowed_domains 和 blocked_domains",
            )

        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT_SEC) as client:
                resp = await client.post(
                    self.DDG_LITE_URL,
                    data={"q": query.strip()},
                    headers={
                        "User-Agent": "MiniCode/1.0",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                resp.raise_for_status()
                html = resp.text
        except httpx.TimeoutException:
            return ToolResult(ok=False, output="", error="搜索请求超时")
        except httpx.RequestError as exc:
            return ToolResult(ok=False, output="", error=f"搜索失败: {exc}")

        # 解析 DDG Lite 结果
        results = self._parse_ddg_lite(html)

        # 过滤
        if allowed_domains:
            domain_set = {d.lower().strip() for d in allowed_domains}
            results = [r for r in results if any(d in r.get("link", "").lower() for d in domain_set)]
        elif blocked_domains:
            domain_set = {d.lower().strip() for d in blocked_domains}
            results = [r for r in results if not any(d in r.get("link", "").lower() for d in domain_set)]

        results = results[:max_results]

        if not results:
            return ToolResult(ok=True, output="未找到匹配结果。")

        lines = [f"QUERY: {query}", ""]
        for i, item in enumerate(results, 1):
            lines.append(f"[{i}] {item.get('title', '(无标题)')}")
            lines.append(f"    URL: {item.get('link', '')}")
            snippet = item.get("snippet", "")
            if snippet:
                lines.append(f"    {snippet[:200]}")
            lines.append("")

        return ToolResult(
            ok=True,
            output="\n".join(lines).strip(),
            artifacts=[{"query": query, "results": len(results)}],
        )

    @staticmethod
    def _parse_ddg_lite(html: str) -> list[dict]:
        """从 DDG Lite HTML 中提取搜索结果。"""
        results: list[dict] = []

        # DDG Lite 结果格式:
        # <a rel="nofollow" href="URL" ...>Title</a>
        # <span class="link-text">显示URL</span>
        # <span class="snippet">摘要</span>
        link_pattern = re.compile(
            r'<a[^>]*href="([^"]*)"[^>]*class="[^"]*result-link[^"]*"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        snippet_pattern = re.compile(
            r'<td class="result-snippet">(.*?)</td>',
            re.IGNORECASE | re.DOTALL,
        )

        # 简化：查找所有外部链接（非 DDG 域名的链接）
        url_pattern = re.compile(
            r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )

        matches = url_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (url, title) in enumerate(matches):
            # 跳过 DDG 自身链接
            if "duckduckgo.com" in url.lower():
                continue
            title_clean = re.sub(r"<[^>]+>", "", title).strip()
            if not title_clean:
                continue
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            results.append({"title": title_clean, "link": url, "snippet": snippet})

        return results
