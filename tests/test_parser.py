import ast
import asyncio
import inspect

from best_practices_rag import parser
from best_practices_rag.parser import (
    GraphBundle,
    TechExtraction,
    build_synthesized_bundle,
    parse_results,
)
from best_practices_rag.search import ExaResult


def test_tech_extraction_importable_from_parser() -> None:
    t = TechExtraction(name="FastAPI")
    assert t.name == "FastAPI"
    assert t.version is None


def test_tech_extraction_with_version() -> None:
    t = TechExtraction(name="FastAPI", version="0.116")
    assert t.version == "0.116"


def test_build_synthesized_bundle_returns_graph_bundle() -> None:
    bundle = build_synthesized_bundle(
        synthesized_content="# Overview\nContent here.",
        tech_names=["fastapi", "sqlalchemy"],
        source_urls=["https://example.com"],
        query="async session management for FastAPI and SQLAlchemy",
    )
    assert isinstance(bundle, GraphBundle)
    assert len(bundle.nodes) > 0
    assert len(bundle.relations) > 0


def test_build_synthesized_bundle_has_best_practice_node() -> None:
    bundle = build_synthesized_bundle(
        synthesized_content="Content.",
        tech_names=["fastapi"],
        source_urls=["https://fastapi.tiangolo.com"],
        query="FastAPI async patterns",
    )
    bp_nodes = [n for n in bundle.nodes if n.label == "BestPractice"]
    assert len(bp_nodes) == 1
    assert bp_nodes[0].properties["body"] == "Content."


def test_build_synthesized_bundle_with_lang_names() -> None:
    bundle = build_synthesized_bundle(
        synthesized_content="Content.",
        tech_names=["fastapi"],
        source_urls=[],
        query="FastAPI patterns",
        lang_names=["python"],
    )
    bp_nodes = [n for n in bundle.nodes if n.label == "BestPractice"]
    assert bp_nodes[0].properties["languages"] == "python"


def test_parse_results_works_with_updated_exa_result() -> None:
    results = [
        ExaResult(
            id="r1",
            url="https://realpython.com/fastapi-guide",
            title="FastAPI Guide",
            summary="A great guide without highlights field",
            published_date="2024-01-01",
            score=0.9,
            text="Full text here",
        )
    ]

    bundle = asyncio.run(parse_results(results, tech_names=["fastapi"]))
    bp_nodes = [n for n in bundle.nodes if n.label == "BestPractice"]
    assert len(bp_nodes) == 1
    assert bp_nodes[0].properties["title"] == "FastAPI Guide"


def test_parse_results_strips_url_fragment() -> None:
    results = [
        ExaResult(
            id="r1",
            url="https://docs.python.org/3/library/asyncio.html#event-loop",
            title="Asyncio",
            summary="Asyncio docs",
            published_date=None,
            score=None,
        )
    ]
    bundle = asyncio.run(parse_results(results, tech_names=["python"]))
    assert all("#" not in n.name for n in bundle.nodes)


def test_parse_results_strips_url_query_string() -> None:
    results = [
        ExaResult(
            id="r2",
            url="https://stackoverflow.com/questions/123?tab=votes",
            title="SO Question",
            summary="Answer summary",
            published_date=None,
            score=None,
        )
    ]
    bundle = asyncio.run(parse_results(results, tech_names=["python"]))
    assert all("?" not in n.name for n in bundle.nodes)


def test_build_synthesized_bundle_stores_tech_versions() -> None:
    bundle = build_synthesized_bundle(
        synthesized_content="Content.",
        tech_names=["fastapi"],
        source_urls=[],
        query="FastAPI patterns",
        tech_versions={"fastapi": "0.116"},
    )
    bp_nodes = [n for n in bundle.nodes if n.label == "BestPractice"]
    assert (
        bp_nodes[0].properties["tech_versions_at_synthesis"] == '{"fastapi": "0.116"}'
    )


def test_build_synthesized_bundle_tech_versions_empty_by_default() -> None:
    bundle = build_synthesized_bundle(
        synthesized_content="Content.",
        tech_names=["fastapi"],
        source_urls=[],
        query="FastAPI patterns",
    )
    bp_nodes = [n for n in bundle.nodes if n.label == "BestPractice"]
    assert bp_nodes[0].properties["tech_versions_at_synthesis"] == ""


def test_parser_does_not_import_from_extraction() -> None:
    source = inspect.getsource(parser)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "best_practices_rag.extraction", (
                    "parser.py must not import from best_practices_rag.extraction"
                )
