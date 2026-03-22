import logging
from typing import Any

from exa_py import Exa
from pydantic import BaseModel

from best_practices_rag.config import get_settings


logger = logging.getLogger(__name__)

_EXA_MAX_RESULTS: int = 5


class ExaResult(BaseModel):
    id: str
    url: str
    title: str
    summary: str
    published_date: str | None
    score: float | None
    text: str | None = None


class ExaSearchError(Exception):
    pass


def search_best_practices(
    query: str,
    num_results: int = _EXA_MAX_RESULTS,
    exclude_domains: list[str] | None = None,
    start_published_date: str | None = None,
    category: str | None = None,
) -> list[ExaResult]:
    """Search Exa for best-practice results matching the query.

    Single-call approach using exa.search() with a contents dict.
    Domain and date filters are passed as top-level kwargs.
    When filter args are None, Settings defaults apply.
    """
    logger.info("Exa search started — query: %r, max_results=%d", query, num_results)
    settings = get_settings()
    exa = Exa(api_key=settings.exa_api_key.get_secret_value())

    effective_exclude = (
        exclude_domains if exclude_domains is not None else settings.exa_exclude_domains
    )

    search_kwargs: dict[str, Any] = {
        "num_results": num_results,
        "type": "neural",
        "contents": {
            "text": {"max_characters": 8000},
            "summary": True,
        },
    }

    if effective_exclude:
        search_kwargs["exclude_domains"] = effective_exclude
    if start_published_date is not None:
        search_kwargs["start_published_date"] = start_published_date
    if category is not None:
        search_kwargs["category"] = category

    try:
        response = exa.search(query, **search_kwargs)
    except Exception as exc:
        if "429" in str(exc):
            raise ExaSearchError("Exa search failed — rate limited (429)")
        raise ExaSearchError("Exa search failed") from None

    raw_results = response.results
    if not raw_results:
        logger.info("Exa search complete — 0 results returned")
        return []

    logger.info("Exa search complete — %d results returned", len(raw_results))

    exa_results = []
    for r in raw_results:
        summary = r.summary if isinstance(r.summary, str) else ""
        exa_results.append(
            ExaResult(
                id=r.id,
                url=r.url,
                title=r.title or "",
                summary=summary,
                published_date=r.published_date,
                score=r.score,
                text=r.text if isinstance(r.text, str) else None,
            )
        )
    return exa_results
