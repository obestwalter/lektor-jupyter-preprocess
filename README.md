# Lektor Jupyter preprocess

Integrate Jupyter notebooks into [Lektor CMS](https://www.getlektor.com/).

## Installation

The plugin is not installable via PyPI (yet), so you have to install it as a [local plugin in the packages folder of your site](https://www.getlektor.com/docs/project-layout/).

## Get the code

### Copy it

Download this folder and copy it into `<your lektor site>/package`.
 
### ... or add as git submodule

    $ mkdir <your lektor site>/packages
    $ cd <your lektor site>/packages
    $ git submodule add https://github.com/obestwalter/lektor-jupyter-preprocess
    
## Get started 

Once you have the plugin in `packages`, run a `lektor clean` and `lektor serve` to start integrating notebook powered articles into your site.  

Have a look at the [example project](example-project) how to configure and use it.

The plugin is in use on my personal website - read more about how it works in the [obligatory meta article about my website](https://oliver.bestwalter.de/articles/website-meta/).

## Warning: minimal implementation

I am mainly using this to render simple notebooks with text output. Anything more involved would need to render directly to HTML, which is likely possible by extending this plugin. The are a few todos in the code already about this.

## If this is not what you want

There is also [lektor-jupyter](https://pypi.org/project/lektor-jupyter/), which does not execute the notebook itself and directly renders it to HTML, instead of being a preprocess step like this one.
