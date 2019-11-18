from pathlib import Path

import pytest

from lektor.project import Project
from lektor_jupyter_preprocess import convert, JupyterPreprocessPlugin

HERE: Path = Path(__file__).parent
ROOT = HERE.parent

@pytest.fixture(scope="session")
def project():
    project = Project.from_path(str(ROOT / "example-project"))
    assert project
    return project

@pytest.fixture(scope="session")
def initialized_project(project):
    env = project.make_env()
    JupyterPreprocessPlugin(env, "dontcare")
    return project

def test_convert_to_markdown(initialized_project):
    """Acceptance test checking against a prepared expectation."""
    inPath = HERE / "code.ipynb"
    outPath = inPath.with_suffix(".md")
    expectationPath = outPath.with_suffix(".exp")
    if outPath.exists():
        outPath.unlink()
    output = convert(inPath)
    outPath.write_text(output)

    expectation = expectationPath.read_text().strip()
    assert isinstance(expectation, str)
    assert isinstance(output, str)
    # todo pycharm: str diff broken => extend/file bug report
    # click to see difference still somehow helps, but really broken obj rep
    assert expectation == output
    outPath.unlink()
