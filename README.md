# Lektor Jupyter preprocess

Integrate Jupyter notebooks into [Lektor CMS](https://www.getlektor.com/).

## Installation

The plugin is not installable via PyPI (yet), so you have to install it as a [local plugin in the packages folder of your site](https://www.getlektor.com/docs/project-layout/).

### Simple way

Download this folder and copy it into `<your lektor site>/package`.
 
### As git submodule

    $ mkdir <your lektor site>/packages
    $ cd <your lektor site>/packages
    $ git submodule add https://github.com/obestwalter/lektor-jupyter-preprocess
    
Once you have the plugin in `packages`, run a `lektor clean` and `lektor serve` to start integrating notebook powered articles into your site.  

Have a look at the [example project](example-project) how to configure and use it.

The plugin is in use on my personal website - read more about how it works in the [obligatory meta article about my website](https://oliver.bestwalter.de/articles/website-meta/).
