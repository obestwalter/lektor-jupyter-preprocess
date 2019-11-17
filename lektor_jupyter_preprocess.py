import logging
import os
from functools import partial
from pathlib import Path
from typing import Optional

import nbconvert
import nbformat
from IPython import InteractiveShell
from IPython.core.magics import CodeMagics
from black import format_str, FileMode
from lektor import build_programs
from lektor.db import Attachment
from lektor.pluginsystem import Plugin
from nbconvert.preprocessors import ExecutePreprocessor

log = logging.getLogger(__name__)

IPYTHON_SHELL = InteractiveShell()
_BLACKIFY = partial(format_str, mode=FileMode(line_length=79))
_already_built = set()  # hack: prevent duplicate builds after clean


def blackify(text):
    """Don't crash if cell contains magic that is not processed."""
    try:
        return _BLACKIFY(text)
    except Exception:
        log.exception("[IGNORE] blackify failed")
        return text


class JupyterPreprocessPlugin(Plugin):
    name = "Jupyter Notebook preprocessor"
    description = (
        "Execute and render a Jupyter notebook. Provide the result in contents.lr."
    )
    JUPYTER_PREPROCESS = "JUPYTER_PREPROCESS"

    def on_setup_env(self, **_):
        """'Replace' attachment build program with an enhanced version.

        `get_build_program` finds this before the inbuilt, effectively shadowing it.

        This makes the preprocessing a part of the build of the page, overwriting
        contents.lr before it is processed, therefore preventing build loops.
        """
        config = self.get_config()
        self.env.jinja_env.globals[self.JUPYTER_PREPROCESS] = {
            "source_url": config.get("source_url"),
            "paths": set(),
        }
        self.env.add_build_program(Attachment, NotebookAwareAttachmentBuildProgram)

    def on_before_build_all(self, **_):
        _already_built.clear()

    def on_before_build(self, source, **_):
        attachments = getattr(source, "attachments", None)
        if not attachments:
            return

        attachment = attachments.get(f"{Path(source.path).name}.ipynb")
        if attachment:
            self.env.jinja_env.globals[self.JUPYTER_PREPROCESS]["paths"].add(
                source.path
            )


class NotebookAwareAttachmentBuildProgram(build_programs.AttachmentBuildProgram):
    def build_artifact(self, artifact):
        path = get_notebook_file_path(artifact.source_obj)
        if path and path not in _already_built:
            md = convert(path)
            dst = path.parent / "contents.lr"
            log.debug(f"{path} -> {dst}")
            dst.write_text(md)
            _already_built.add(path)
        super().build_artifact(artifact)


def get_notebook_file_path(source_obj) -> Optional[Path]:
    """Fetch notebook path if page is notebook powered."""
    try:
        # Can this ever fail? Not sure - erring on the side of paranoid.
        filename = source_obj.contents.filename
    except AttributeError:
        return

    path = Path(filename)
    candidate = path.parent / f"{path.parent.name}.ipynb"
    if candidate.exists():
        return candidate


def convert(path: Path) -> str:
    filename = path.name
    log.info(f"convert to markdown: {filename}")
    cwd = path.parent
    nb = nbformat.reads(path.read_text(), as_version=4)
    oldCwd = os.getcwd()
    try:
        os.chdir(cwd)
        ArticleExecutePreprocessor().preprocess(nb)
    finally:
        os.chdir(oldCwd)
    return nbconvert.MarkdownExporter().from_notebook_node(nb)[0]


class ArticleExecutePreprocessor(ExecutePreprocessor):
    """Apply load magic and massage the markdown output."""

    def preprocess_cell(self, cell, resources, cell_index, store_history=True):
        if cell.cell_type != "code":
            return cell, resources

        first_line = cell.source.strip().splitlines()[0]
        load_candidate = first_line.replace("# ", "")
        if load_candidate.startswith("%load"):
            cell.source = self.apply_load_magic(load_candidate)
        cell.source = blackify(cell.source)
        lp = cell.metadata.get("lektor-preprocess")
        if lp and lp.get("prevent-execution"):
            return cell, resources

        outs = self.run_cell(cell, cell_index, store_history)[1]
        # TODO this could be a different language - read lang from notebook
        new = [f"\n\n```python\n{cell.source}\n```"]
        # TODO make all of these configurable
        for o in outs:
            if o.output_type == "execute_result":
                # TODO pass everything else through as HTML directly
                data = o.data["text/plain"]
                new.append(f"```text\n[result]\n{data}\n```")
            elif o.output_type == "error":
                new.append(f"```text\n[{o.ename}]\n{o.evalue}\n```")
            elif o.output_type == "stream":
                new.append(f"```text\n[{o.name}]\n{o.text}\n```")
            else:
                raise TypeError(f"{o.output_type=} unknown - {cell.source=}")
        cell = nbformat.NotebookNode(
            {"cell_type": "raw", "metadata": {}, "source": "\n".join(new)}
        )
        return cell, resources

    @staticmethod
    def apply_load_magic(content):
        """Apply the %load magic manually.

        Cell magic is not part of preprocessor.

        Feels horribly wrong, but works well enough.
        """
        magic = CodeMagics(shell=IPYTHON_SHELL)
        arg_s = " ".join(content.split()[1:])
        magic.load(arg_s)
        code = IPYTHON_SHELL.rl_next_input
        return code
