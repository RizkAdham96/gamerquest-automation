import ast
from pathlib import Path

SOURCE = Path("automation.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
FUNCTIONS = {
    node.name: node
    for node in TREE.body
    if isinstance(node, ast.FunctionDef)
}


def test_story_level_duplicate_guard_exists():
    assert "is_duplicate_news_topic" in FUNCTIONS, (
        "News currently deduplicates mainly by source URL; "
        "it needs a story/topic-level duplicate guard."
    )


def test_image_relevance_guard_exists():
    assert "source_image_matches_article" in FUNCTIONS, (
        "News currently accepts source-page artwork without "
        "checking that it matches the generated article topic."
    )


def test_contradiction_guard_exists():
    assert "has_conflicting_news_claims" in FUNCTIONS, (
        "News needs a guard against publishing materially "
        "conflicting claims for an already-covered topic."
    )
