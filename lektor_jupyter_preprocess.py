import logging
import os
import sys
from typing import Optional

from functools import partial
from pathlib import Path

import nbconvert
import nbformat
from black import format_str, FileMode
from IPython import InteractiveShell
from IPython.core.magics import CodeMagics
from nbconvert.preprocessors import ExecutePreprocessor
from lektor import build_programs
from lektor.db import Attachment
from lektor.pluginsystem import Plugin

log = logging.getLogger(__name__)

IPYTHON_SHELL = InteractiveShell()
BLACK = partial(format_str, mode=FileMode(line_length=79))


class JupyterPreprocessPlugin(Plugin):
    name = "Jupyter Notebook preprocessor"
    description = (
        "Execute and render a Jupyter notebook. Provide the result in contents.lr."
    )
    _GLOBALS_KEY = "JUPYTER_PREPROCESS"

    def on_setup_env(self, **_):
        """'Replace' attachment build program by an enhanced version.

        `get_build_program` finds this before the inbuilt, effectively shadowing it.

        This makes the preprocessing a part of the build of the page, overwriting
        contents.lr before it is process, preventing build loops.
        """
        config = self.get_config()
        self.env.jinja_env.globals[self._GLOBALS_KEY] = {
            "source_url": config.get("source_url")
        }
        self.env.add_build_program(Attachment, NotebookAwareAttachmentBuildProgram)

    def on_before_build(self, source, **_):
        g = self.env.jinja_env.globals[self._GLOBALS_KEY]
        attachments = getattr(source, "attachments", None)
        if not attachments:
            g["from_notebook"] = False
            return

        for attachment in source.attachments:
            g["from_notebook"] = bool(get_attached_notebook_path(attachment))


class NotebookAwareAttachmentBuildProgram(build_programs.AttachmentBuildProgram):
    def build_artifact(self, artifact):
        path = get_attached_notebook_path(artifact.source_obj)
        if path:
            md = convert(path)
            dst = path.parent / "contents.lr"
            log.debug(f"{path} -> {dst}")
            dst.write_text(md)
        super().build_artifact(artifact)


def get_attached_notebook_path(source_obj) -> Optional[Path]:
    """If this is a notebook powered page: return path to the notebook."""
    try:
        filename = source_obj.contents.filename
    except AttributeError:
        return

    if not filename.endswith(".ipynb"):
        return

    try:
        parent = source_obj.parent.path
    except AttributeError:
        return

    candidate = Path(filename)
    if candidate.stem != Path(parent).name:
        return

    return candidate


def convert(path: Path) -> str:
    filename = path.name
    log.info(f"convert to markdown: {filename}")
    cwd = path.parent
    resources = {"nbPath": f"{cwd.name}/{filename}"}
    nb = nbformat.reads(path.read_text(), as_version=4)
    oldCwd = os.getcwd()
    try:
        os.chdir(cwd)
        preproc = ArticleExecutePreprocessor(resources=resources)
        preproc.preprocess(nb, resources=resources)
    finally:
        os.chdir(oldCwd)
    return nbconvert.MarkdownExporter().from_notebook_node(nb, resurces=resources)[0]


class ArticleExecutePreprocessor(ExecutePreprocessor):
    """Apply load magic and massage the markdown output.

    I'm sure there are more elegant ways, but this works for me atm.
    """

    def preprocess(self, nb, resources=None, km=None):
        # cell = self._lektor_prepare_info(resources=resources)
        # if cell:
        #     nb.cells.append(cell)
        super().preprocess(nb, resources=resources, km=km)

    # @staticmethod
    # def _lektor_prepare_info(resources):
    #     text = resources["info"]
    #     if not text:
    #         return
    #
    #     bits = {"version": f"{sys.version_info.major}.{sys.version_info.minor}"}
    #     try:
    #         text = text.format_map(bits)
    #     except Exception:
    #         log.exception(f"[IGNORE] formatting from bits {bits} went wrong.")
    #     data = {"source": text, "cell_type": "markdown", "metadata": {}}
    #     return nbformat.NotebookNode(data)

    def preprocess_cell(self, cell, resources, cell_index, store_history=True):
        if cell.cell_type != "code":
            return cell, resources

        assert isinstance(cell.source, str)
        load_candidate = cell.source.replace("# ", "")
        # TODO make running and magic application configurable
        if load_candidate.startswith("%load"):
            cell.source = BLACK(self.apply_load_magic(load_candidate))
            return cell, resources

        _, outs = self.run_cell(cell, cell_index, store_history)
        # TODO this could be something else - read lang from notebook
        new = [f"\n\n```python\n{BLACK(cell.source)}\n```"]
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
                raise Exception(f"dunno what to do with: {o}")
        cell = nbformat.NotebookNode(
            {"cell_type": "raw", "metadata": {}, "source": "\n".join(new)}
        )
        return cell, resources

    @staticmethod
    def apply_load_magic(content):
        """Apply the %load magic manually.

        Cell magic is not automatically applied by
        the preprocessor, so I do this directly here.

        I'm sure this is horribly wrong, but it works well enough.
        """
        magic = CodeMagics(shell=IPYTHON_SHELL)
        arg_s = " ".join(content.split()[1:])
        magic.load(arg_s)
        code = IPYTHON_SHELL.rl_next_input
        return code
