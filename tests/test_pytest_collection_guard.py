"""Regression tests ensuring pytest discovery configuration strictly isolates tests/.

Verifies:
1. Pytest configuration section exists in pyproject.toml.
2. Configured test discovery directory is exclusively tests/.
3. norecursedirs excludes scratch/, scripts/, and other non-test folders.
4. Running `pytest --collect-only` via subprocess does not collect diagnostic or scratch scripts.
"""

from pathlib import Path
import subprocess
import sys
import tomllib

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_pytest_configuration_exists_in_pyproject():
    """Verify [tool.pytest.ini_options] section exists in pyproject.toml."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml not found"

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    assert "tool" in data, "No [tool] section in pyproject.toml"
    assert "pytest" in data["tool"], "No [tool.pytest] section in pyproject.toml"
    assert "ini_options" in data["tool"]["pytest"], "No [tool.pytest.ini_options] section in pyproject.toml"


def test_testpaths_configured_to_tests_directory():
    """Verify testpaths is set to ['tests']."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    pytest_opts = data["tool"]["pytest"]["ini_options"]
    assert "testpaths" in pytest_opts, "testpaths not defined in [tool.pytest.ini_options]"
    assert pytest_opts["testpaths"] == ["tests"], f"Expected testpaths to be ['tests'], got {pytest_opts['testpaths']}"


def test_norecursedirs_excludes_scratch_and_scripts():
    """Verify norecursedirs excludes scratch/, scripts/, and non-test directories."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    pytest_opts = data["tool"]["pytest"]["ini_options"]
    assert "norecursedirs" in pytest_opts, "norecursedirs not defined in [tool.pytest.ini_options]"

    excluded = set(pytest_opts["norecursedirs"])
    assert "scratch" in excluded, "scratch directory must be excluded in norecursedirs"
    assert "scripts" in excluded, "scripts directory must be excluded in norecursedirs"
    assert ".venv" in excluded, ".venv directory must be excluded in norecursedirs"
    assert "data" in excluded, "data directory must be excluded in norecursedirs"
    assert "documents" in excluded, "documents directory must be excluded in norecursedirs"


def test_pytest_collect_only_subprocess_excludes_scratch_and_scripts():
    """Verify pytest --collect-only does not collect diagnostic or scratch scripts."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"pytest --collect-only failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

    output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    # Ensure no items from scratch/ or scripts/ were collected
    for line in output_lines:
        assert not line.startswith("scratch/"), f"Unexpected scratch item collected: {line}"
        assert not line.startswith("scratch\\"), f"Unexpected scratch item collected: {line}"
        assert not line.startswith("scripts/"), f"Unexpected scripts item collected: {line}"
        assert not line.startswith("scripts\\"), f"Unexpected scripts item collected: {line}"

    # Specifically check known diagnostic script names are absent
    disallowed_patterns = [
        "test_combined_hybrid_flow",
        "test_pymupdf4llm",
        "test_parse_doc",
        "test_extract_tables_first",
        "test_candidate_matches",
        "test_refinements",
        "test_policy_simulation",
        "test_qr_call",
        "test_rewrites_live",
    ]
    stdout_text = result.stdout
    for pattern in disallowed_patterns:
        assert pattern not in stdout_text, f"Diagnostic script '{pattern}' was collected by pytest!"

    # Ensure valid tests in tests/ ARE collected
    assert any("tests/test_chunking_pipeline.py" in line or "tests\\test_chunking_pipeline.py" in line for line in output_lines), (
        "Expected tests/test_chunking_pipeline.py in collected output"
    )
