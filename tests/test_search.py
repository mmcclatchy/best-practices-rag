from typing import Any

import pytest
from pytest_mock import MockerFixture

from best_practices_rag.search import ExaResult, ExaSearchError, search_best_practices


def _make_mock_result(
    mocker: MockerFixture,
    id: str = "r1",
    url: str = "https://example.com",
    title: str = "Test Title",
    summary: str = "Test summary",
    published_date: str | None = "2024-01-01",
    score: float | None = 0.9,
    text: str | None = "Full text",
) -> Any:
    r = mocker.MagicMock()
    r.id = id
    r.url = url
    r.title = title
    r.summary = summary
    r.published_date = published_date
    r.score = score
    r.text = text
    return r


def _make_mock_exa_response(mocker: MockerFixture, results: list) -> Any:
    resp = mocker.MagicMock()
    resp.results = results
    return resp


def test_exa_result_has_summary_field() -> None:
    r = ExaResult(
        id="1",
        url="https://example.com",
        title="Title",
        summary="A summary",
        published_date=None,
        score=None,
    )
    assert r.summary == "A summary"


def test_exa_result_has_no_highlights_field() -> None:
    assert "highlights" not in ExaResult.model_fields


def test_search_uses_single_call_with_contents_dict(mocker: MockerFixture) -> None:
    mock_result = _make_mock_result(mocker)
    mock_response = _make_mock_exa_response(mocker, [mock_result])
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.return_value = mock_response
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_content_top_n = 5
    settings.exa_exclude_domains = ["w3schools.com"]
    settings.exa_min_published_year_offset = 2
    settings.exa_min_score = 0.0
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    search_best_practices("FastAPI async patterns")

    call_kwargs = mock_exa_instance.search.call_args[1]
    assert "contents" in call_kwargs
    assert isinstance(call_kwargs["contents"], dict)
    assert "text" in call_kwargs["contents"]
    assert call_kwargs["contents"]["text"]["max_characters"] == 8000
    assert call_kwargs["contents"].get("summary") is True


def test_search_passes_type_neural_by_default(mocker: MockerFixture) -> None:
    mock_result = _make_mock_result(mocker)
    mock_response = _make_mock_exa_response(mocker, [mock_result])
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.return_value = mock_response
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_content_top_n = 5
    settings.exa_exclude_domains = []
    settings.exa_min_published_year_offset = 2
    settings.exa_min_score = 0.0
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    search_best_practices("FastAPI async patterns")

    call_kwargs = mock_exa_instance.search.call_args[1]
    assert call_kwargs.get("type") == "neural"


def test_search_passes_exclude_domains_as_kwarg(mocker: MockerFixture) -> None:
    mock_result = _make_mock_result(mocker)
    mock_response = _make_mock_exa_response(mocker, [mock_result])
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.return_value = mock_response
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_content_top_n = 5
    settings.exa_exclude_domains = ["w3schools.com"]
    settings.exa_min_published_year_offset = 2
    settings.exa_min_score = 0.0
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    search_best_practices(
        "query",
        exclude_domains=["geeksforgeeks.org"],
    )

    call_kwargs = mock_exa_instance.search.call_args[1]
    assert call_kwargs.get("exclude_domains") == ["geeksforgeeks.org"]


def test_search_passes_start_published_date_as_kwarg(mocker: MockerFixture) -> None:
    mock_result = _make_mock_result(mocker)
    mock_response = _make_mock_exa_response(mocker, [mock_result])
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.return_value = mock_response
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_content_top_n = 5
    settings.exa_exclude_domains = ["w3schools.com"]
    settings.exa_min_published_year_offset = 2
    settings.exa_min_score = 0.0
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    search_best_practices("query", start_published_date="2024-01-01")

    call_kwargs = mock_exa_instance.search.call_args[1]
    assert call_kwargs.get("start_published_date") == "2024-01-01"


def test_search_falls_back_to_settings_exclude_domains_when_none(
    mocker: MockerFixture,
) -> None:
    mock_result = _make_mock_result(mocker)
    mock_response = _make_mock_exa_response(mocker, [mock_result])
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.return_value = mock_response
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_content_top_n = 5
    settings.exa_exclude_domains = ["w3schools.com", "medium.com"]
    settings.exa_min_published_year_offset = 2
    settings.exa_min_score = 0.0
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    search_best_practices("query")

    call_kwargs = mock_exa_instance.search.call_args[1]
    assert call_kwargs.get("exclude_domains") == ["w3schools.com", "medium.com"]


def test_search_raises_on_rate_limit(mocker: MockerFixture) -> None:
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.side_effect = Exception("HTTP 429 Too Many Requests")
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_content_top_n = 5
    settings.exa_exclude_domains = []
    settings.exa_min_score = 0.0
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    with pytest.raises(ExaSearchError, match="rate limited"):
        search_best_practices("query")


def test_search_raises_on_generic_error(mocker: MockerFixture) -> None:
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.side_effect = Exception("connection refused")
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_content_top_n = 5
    settings.exa_exclude_domains = []
    settings.exa_min_score = 0.0
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    with pytest.raises(ExaSearchError, match="Exa search failed"):
        search_best_practices("query")


def test_search_returns_empty_list_when_no_results(mocker: MockerFixture) -> None:
    mock_response = _make_mock_exa_response(mocker, [])
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.return_value = mock_response
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_content_top_n = 5
    settings.exa_exclude_domains = []
    settings.exa_min_score = 0.0
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    results = search_best_practices("query")

    assert results == []


def test_search_generic_error_preserves_cause(mocker: MockerFixture) -> None:
    original_exc = Exception("connection refused")
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.side_effect = original_exc
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_exclude_domains = []
    settings.exa_min_score = 0.0
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    with pytest.raises(ExaSearchError) as exc_info:
        search_best_practices("query")

    assert exc_info.value.__cause__ is original_exc


def test_search_returns_exa_result_list(mocker: MockerFixture) -> None:
    mock_result = _make_mock_result(
        mocker,
        id="r1",
        url="https://realpython.com/article",
        title="FastAPI Guide",
        summary="Great summary",
        published_date="2024-06-01",
        score=0.95,
        text="Full text content",
    )
    mock_response = _make_mock_exa_response(mocker, [mock_result])
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.return_value = mock_response
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_content_top_n = 5
    settings.exa_exclude_domains = []
    settings.exa_min_published_year_offset = 2
    settings.exa_min_score = 0.0
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    results = search_best_practices("query")

    assert len(results) == 1
    assert isinstance(results[0], ExaResult)
    assert results[0].url == "https://realpython.com/article"
    assert results[0].summary == "Great summary"


def test_search_filters_results_below_min_score(mocker: MockerFixture) -> None:
    results_data = [
        _make_mock_result(mocker, id="r1", url="https://a.com", score=0.9),
        _make_mock_result(mocker, id="r2", url="https://b.com", score=0.7),
        _make_mock_result(mocker, id="r3", url="https://c.com", score=0.3),
    ]
    mock_response = _make_mock_exa_response(mocker, results_data)
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.return_value = mock_response
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_exclude_domains = []
    settings.exa_min_score = 0.5
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    results = search_best_practices("query")

    assert len(results) == 2
    assert all(r.score is not None and r.score >= 0.5 for r in results)


def test_search_no_filtering_when_min_score_zero(mocker: MockerFixture) -> None:
    results_data = [
        _make_mock_result(mocker, id="r1", url="https://a.com", score=0.9),
        _make_mock_result(mocker, id="r2", url="https://b.com", score=0.1),
        _make_mock_result(mocker, id="r3", url="https://c.com", score=0.0),
    ]
    mock_response = _make_mock_exa_response(mocker, results_data)
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.return_value = mock_response
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_exclude_domains = []
    settings.exa_min_score = 0.0
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    results = search_best_practices("query")

    assert len(results) == 3


def test_search_filters_results_with_none_score(mocker: MockerFixture) -> None:
    results_data = [
        _make_mock_result(mocker, id="r1", url="https://a.com", score=0.9),
        _make_mock_result(mocker, id="r2", url="https://b.com", score=None),
    ]
    mock_response = _make_mock_exa_response(mocker, results_data)
    mock_exa_instance = mocker.MagicMock()
    mock_exa_instance.search.return_value = mock_response
    mocker.patch("best_practices_rag.search.Exa", return_value=mock_exa_instance)

    settings = mocker.MagicMock()
    settings.exa_api_key.get_secret_value.return_value = "test_key"
    settings.exa_exclude_domains = []
    settings.exa_min_score = 0.5
    mocker.patch("best_practices_rag.search.get_settings", return_value=settings)

    results = search_best_practices("query")

    assert len(results) == 1
    assert results[0].url == "https://a.com"
