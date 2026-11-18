from ddgs import DDGS


def web_search(query: str, max_results: int = 3) -> dict:
    """Search the web and return relevant results.

    Args:
        query: The search query.
        max_results: Maximum number of results to retrieve.

    Returns:
        A dictionary containing search results or an error.
    """
    if not query.strip():
        return {
            "status": "error",
            "message": "Search query cannot be empty.",
        }

    max_results = max(1, min(max_results, 5))

    try:
        results = DDGS().text(query, max_results=max_results)

        return {
            "status": "success",
            "query": query,
            "results": results,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
        }