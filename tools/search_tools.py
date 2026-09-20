from __future__ import annotations

from typing import Optional, List, Dict, Any

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None


class SearchTools:
    """
    Dedicated handler for free web search powered by DuckDuckGo (ddgs).
    Enables coding agents to search technical documentation, error messages,
    API references, and open-source libraries without requiring paid API keys.
    """

    def __init__(self):
        pass

    def search_web(self, query: str, max_results: int = 5) -> str:
        """Search the web using DuckDuckGo for live documentation, APIs, error solutions, or technical references without API keys.

        Args:
            query: The search query to look up (e.g. 'FastAPI lifespan handlers', 'Tailwind v4 grid syntax').
            max_results: Maximum number of search results to return (default: 5, clamped between 1 and 10).

        Returns:
            A formatted markdown summary of top web search results with titles, links, and snippets.
        """
        if not query or not query.strip():
            return "Error: query parameter must not be empty."

        clean_query = query.strip()

        try:
            count = int(max_results)
        except (ValueError, TypeError):
            count = 5
        count = max(1, min(10, count))

        if DDGS is None:
            return "Error: duckduckgo search library is not installed. Please run `pip install ddgs`."

        try:
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(clean_query, max_results=count))
        except Exception as e:
            return f"Search error: Unable to retrieve results for '{clean_query}' ({type(e).__name__}: {str(e)}). Please try again or refine your query."

        if not raw_results:
            return f"No web results found for query: '{clean_query}'"

        lines: List[str] = [f"### Web Search Results for: \"{clean_query}\"\n"]
        for i, item in enumerate(raw_results, 1):
            title = item.get("title", "Untitled").strip()
            url = item.get("href") or item.get("link") or ""
            body = item.get("body") or item.get("snippet") or ""
            body = body.strip()

            if url:
                lines.append(f"{i}. **[{title}]({url})**")
            else:
                lines.append(f"{i}. **{title}**")

            if body:
                lines.append(f"   {body}")
            lines.append("")

        return "\n".join(lines).strip()
