from pathlib import Path

from setuptools import setup, find_packages

setup(
    name="lektor-jupyter-preprocess",
    version="0.1",
    author="Oliver Bestwalter",
    author_email="olver@bestwalter.de",
    python_requires=">=3.6",
    install_requires=["jupyter"],
    keywords="Lektor plugin Jupyter markdown",
    license="MIT",
    description=(
        "Execute and render a Jupyter notebook. Provide the result in contents.lr."
    ),
    long_description=(Path(__file__).parent / "README.md").read_text(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    py_modules=["lektor_jupyter_preprocess"],
    # url='[link to your repository]', # FIXME
    classifiers=["Framework :: Lektor", "Environment :: Plugins"],
    entry_points={
        "lektor.plugins": [
            "jupyter-preprocess = lektor_jupyter_preprocess:JupyterPreprocessPlugin"
        ]
    },
)
