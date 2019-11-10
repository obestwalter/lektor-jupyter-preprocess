from pathlib import Path

from lektor_jupyter_preprocess import convert

HERE: Path = Path(__file__).parent

def test_convert_to_markdown():
    """Acceptance test checking against a prepared expectation."""
    inPath = HERE / "code.ipynb"
    outPath = inPath.with_suffix(".md")
    expectationPath = outPath.with_suffix(".exp")
    if outPath.exists():
        outPath.unlink()
    output = convert(inPath)
    outPath.write_text(output)
    expectation = expectationPath.read_text()
    assert expectation == output
    outPath.unlink()
