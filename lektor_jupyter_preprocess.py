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

PLUGIN_KEY = "JUPYTER_PREPROCESS"
config = {
    "url.source": None,
    "metadata.blackify": True,
    "metadata.execute": True,
    # todo figure out how jupyter does these things and play together with it
    "metadata.allow_errors": False,
    "metadata.full_traceback": True,
    "cell.source": "\n\n```{language}\n{cell.source}\n```",
    # TODO figure out, why node.data[text/plain] is correct (no quotes around key!1?!?)
    "node.execute_result": "```text\n[result]\n{node.data[text/plain]}\n```",
    "node.stream": "```text\n[{node.name}]\n{node.text}\n```",
    "node.exception": "```text\n[{node.ename}]\n{node.evalue}\n```",
}
f"""configuration of the plugin.

This dict should define all existing keys and provide sane defaults (sane for me).

It can be overridden in these ways (sorted by order of precedence - last one wins):

* config values from configs/jupyter-preprocess.ini
* dict at {PLUGIN_KEY} in notebook metadata
* dict at {PLUGIN_KEY} in cell metadata
* dict literal on second line in a cell using the %load magic

See example-project/jupyter-preprocess.ini and tests/code.ipynb for examples
"""


class JupyterPreprocessPlugin(Plugin):
    name = "Jupyter Notebook preprocessor"
    description = (
        "Execute and render a Jupyter notebook. Provide the result in contents.lr."
    )

    def on_setup_env(self, **_):
        """'Replace' attachment build program with an enhanced version.

        `get_build_program` finds this before the inbuilt, effectively shadowing it.

        This makes the preprocessing a part of the build of the page, overwriting
        contents.lr before it is processed, therefore preventing build loops.
        """
        update_global_config(self.get_config().to_dict())
        self.env.jinja_env.globals[PLUGIN_KEY] = {
            "url_source": config["url.source"],
            "paths": set(),
        }
        self.env.add_build_program(Attachment, NotebookAwareAttachmentBuildProgram)

    def on_before_build_all(self, **_):  # noqa
        _already_built.clear()

    def on_before_build(self, source, **_):
        attachments = getattr(source, "attachments", None)
        if not attachments:
            return

        attachment = attachments.get(f"{Path(source.path).name}.ipynb")
        if attachment:
            self.env.jinja_env.globals[PLUGIN_KEY]["paths"].add(source.path)


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


def update_global_config(config_):
    global config
    config.update(config_)
    config = {n: fix_inifile_data(v) for n, v in config.items()}


def fix_inifile_data(obj):
    if not isinstance(obj, str):
        return obj

    # inifile escapes control characters - I need them like they where
    obj = obj.encode().decode("unicode_escape")
    # coerce usual suspects to bool
    if obj in ["True", "true", "Yes", "yes", "1", "YES, PLEASE!"]:
        obj = True
    if obj in ["False", "false", "No", "no", "0", "Are you joking?"]:
        obj = False
    return obj


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

    def preprocess_cell(self, cell, resources, *args, **kwargs):
        if cell.cell_type != "code":
            return cell, resources

        cell = pre_process(cell)
        cell_config = {
            **config,
            **self.nb.metadata.get(PLUGIN_KEY, {}),
            **cell.metadata.get(PLUGIN_KEY, {}),
        }
        log.debug("final config for cell is:\n%s", config)
        language = self.nb.metadata.kernelspec.language
        if config["metadata.blackify"] and language == "python":
            cell.source = blackify(cell.source)
        if cell_config["metadata.execute"]:
            nodes = self.run_cell(cell, *args, **kwargs)[1]
        else:
            nodes = cell.outputs
        cell = post_process(language, cell, nodes, cell_config)
        return cell, resources


def pre_process(cell):
    """Apply magics and update cell level config overrides."""
    cell.source = cell.source.strip()
    if not cell.source:
        return cell

    assert isinstance(cell.source, str), f"bad source type: {type(cell.source)}"
    lines = cell.source.strip().splitlines()
    load_candidate = lines[0].replace("# ", "")
    # TODO apply other magics (e.g. %%capture)?
    #  also: is there a more "official" way?
    if load_candidate.startswith("%load"):
        try:
            metadata_override = lines[1]
        except IndexError:
            metadata_override = None
        if metadata_override:
            try:
                metadata_override = eval(metadata_override)
            except Exception:
                log.exception(f"[IGNORE] eval of '{metadata_override}' failed")
            if isinstance(metadata_override, dict):
                cell.metadata[PLUGIN_KEY] = {
                    **cell.metadata.get(PLUGIN_KEY, {}),
                    **metadata_override,
                }
        cell.source = apply_load_magic(load_candidate)
    return cell


def blackify(text):
    """Don't crash if cell contains magic that is not processed."""
    try:
        return _BLACKIFY(text)
    except Exception:
        log.exception("[IGNORE] blackify failed")
        return text


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


def post_process(language, cell, nodes, cell_config) -> nbformat.NotebookNode:
    """Construct what should be written to the contents for this cell.

    This simply creates a new raw cell containing everything - not because it's the
    best solution but the easiest for my use case.

    TODO figure out a better way that also accommodates potential HTML/interactive
     output better Modifies cell in-place (#4).
    """
    out = [config["cell.source"].format(language=language, cell=cell)]
    for node in nodes:
        assert isinstance(node, nbformat.NotebookNode)
        # https://nbformat.readthedocs.io/en/latest/format_description.html
        if node.output_type == "execute_result":
            out.append(config["node.execute_result"].format(node=node))
        elif node.output_type == "stream":
            # TODO use tags/raises-exception like in pytest (not raising raises error)
            #  if <wherever that tags thing is> is set:
            #      raise DidNotRaise(f"should have raised but didn't:\n{node}")
            out.append(config["node.stream"].format(node=node))
        elif node.output_type == "error":
            if not cell_config["metadata.allow_errors"]:
                raise ErrorsNotAllowed(f"raised but errors not allowed:\n{node}")
            if cell_config["metadata.full_traceback"]:
                # TODO handle ANSI terminal colors stuff
                #  see if how jupyter does it is reusable
                #  to keep colours this would need to be HTML though
                out.append("".join(node.traceback))
            else:
                out.append(config["node.exception"].format(node=node))
        else:
            raise UnhandledOutputType(f"{node.output_type=} unknown - {cell.source=}")
    return nbformat.NotebookNode(
        {"cell_type": "raw", "metadata": {}, "source": "\n".join(out)}
    )


class JupyterPreprocessError(Exception):
    """All errors raised by this plugin."""


class UnhandledOutputType(Exception):
    """Something the plugin can't handle (yet)."""


class ErrorsNotAllowed(JupyterPreprocessError):
    """Raised when execution raised exception but errors are not allowed."""


class DidNotRaise(JupyterPreprocessError):
    """Raised when execution should have raised exception error but didn't."""
