"""Unit tests for ctags MCP server tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from server.ctags_server import (
    CodebaseToolError,
    CtagsTool,
    TagEntry,
    _extract_excmd,
    resolve_repo_root,
)

SAMPLE_TAGS_CONTENT = """!_TAG_FILE_FORMAT\t2\t/extended format/
!_TAG_FILE_SORTED\t1\t/0=unsorted, 1=sorted, 2=foldcase/
!_TAG_KIND_DESCRIPTION!Python\tf,function\t/functions/
!_TAG_KIND_DESCRIPTION!Python\tc,class\t/classes/
!_TAG_KIND_DESCRIPTION!Python\tv,variable\t/variables/
calculate_sum\tsrc/calc.py\t5;"\tf\tlanguage:Python\tline:5\tend:6\troles:def
Calculator\tsrc/calc.py\t1;"\tc\tlanguage:Python\tline:1\tend:3\troles:def
PI\tsrc/calc.py\t8;"\tv\tlanguage:Python\tline:8\troles:def
Helper\tsrc/utils.py\t1;"\tc\tlanguage:Python\tline:1\tend:2\troles:def
"""


@pytest.fixture
def repo_dir(tmp_path: Path) -> Path:
    """Creates a temporary workspace structure."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    calc_py = src_dir / "calc.py"
    calc_py.write_text(
        "class Calculator:\n"
        "    def __init__(self):\n"
        "        pass\n"
        "\n"
        "def calculate_sum(a, b):\n"
        "    return a + b\n"
        "\n"
        "PI = 3.14159\n",
        encoding="utf-8",
    )
    utils_py = src_dir / "utils.py"
    utils_py.write_text("class Helper:\n    pass\n", encoding="utf-8")
    return tmp_path


def test_extract_excmd():
    line, pattern = _extract_excmd('42;"')
    assert line == 42
    assert pattern == ""

    line, pattern = _extract_excmd("42;/^def calculate_sum$/")
    assert line == 42
    assert pattern == "/^def calculate_sum$/"

    line, pattern = _extract_excmd("/^def my_func()$/")
    assert line is None
    assert pattern == "def my_func()"


def test_tag_entry_matches():
    entry = TagEntry(
        name="my_func",
        file_path="src/app.py",
        line=10,
        end_line=20,
        pattern="",
        kind_code="f",
        kind_name="function",
        language="Python",
        scope="",
        roles="def",
    )
    assert entry.matches_kind("function")
    assert entry.matches_kind("f")
    assert not entry.matches_kind("class")
    assert entry.matches_language("Python")
    assert entry.matches_language("python")
    assert not entry.matches_language("Rust")

    summary = entry.format_summary()
    assert "src/app.py:10" in summary
    assert "my_func" in summary
    assert "function" in summary


def test_resolve_safe_path(repo_dir: Path):
    tool = CtagsTool(repo_dir)
    safe = tool._resolve_safe_path("src/calc.py")
    assert safe == (repo_dir / "src/calc.py").resolve()

    with pytest.raises(CodebaseToolError, match="Security violation"):
        tool._resolve_safe_path("../escaped.txt")


def test_search_and_list_symbols(repo_dir: Path):
    tags_file = repo_dir / "tags"
    tags_file.write_text(SAMPLE_TAGS_CONTENT, encoding="utf-8")

    tool = CtagsTool(repo_dir)

    # Search for calculate_sum
    result = tool.search_symbols(query="calculate_sum")
    assert "src/calc.py:5" in result
    assert "calculate_sum" in result

    # Search with kind filter
    result_kind = tool.search_symbols(query="Calculator", kind="class")
    assert "Calculator" in result_kind
    assert "calc.py:1" in result_kind

    # Search with non-matching kind
    result_none = tool.search_symbols(query="Calculator", kind="function")
    assert "No symbols matching" in result_none

    # Search with code context snippet
    result_context = tool.search_symbols(query="calculate_sum", include_context=True)
    assert "def calculate_sum(a, b):" in result_context

    # List symbols under src/
    list_res = tool.list_symbols(path="src")
    assert "Indexed Symbols under `src`" in list_res
    assert "Calculator" in list_res
    assert "Helper" in list_res

    # List symbols under specific file
    list_calc = tool.list_symbols(path="src/calc.py")
    assert "Calculator" in list_calc
    assert "Helper" not in list_calc


def test_missing_tags_file(repo_dir: Path):
    tool = CtagsTool(repo_dir)
    res = tool.search_symbols(query="test")
    assert "No Ctags file" in res

    list_res = tool.list_symbols()
    assert "No Ctags file" in list_res


def test_generate_ctags(repo_dir: Path):
    tool = CtagsTool(repo_dir)

    # If universal-ctags exists on the machine, test real generation
    if tool._detect_ctags_binary() is not None:
        res = tool.generate_ctags()
        assert "Generated 'tags'" in res or "already exists" in res
        assert (repo_dir / "tags").exists()

        # Calling again without force
        res_cached = tool.generate_ctags(force=False)
        assert "already exists" in res_cached

        # Calling with force
        res_forced = tool.generate_ctags(force=True)
        assert "Generated 'tags'" in res_forced


def test_generate_ctags_binary_not_found(repo_dir: Path):
    tool = CtagsTool(repo_dir)
    with patch.object(tool, "_detect_ctags_binary", return_value=None):
        res = tool.generate_ctags()
        assert "Error: No compatible Universal Ctags or Exuberant Ctags binary found" in res


def test_resolve_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CTAGS_REPO_ROOT", str(tmp_path))
    assert resolve_repo_root() == tmp_path.resolve()

    monkeypatch.delenv("CTAGS_REPO_ROOT")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert resolve_repo_root() == tmp_path.resolve()
