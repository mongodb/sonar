# -*- coding: utf-8 -*-

from typing import Dict

import jinja2


def render(path: str, template_name: str, parameters: Dict[str, str]) -> str:
    """Returns a rendered Dockerfile.

    path indicates where in the filesystem the Dockerfiles are.
    template_name references a Dockerfile.<template_name> to render.
    """
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(path), undefined=jinja2.StrictUndefined
    )

    return env.get_template("Dockerfile.{}".format(template_name)).render(parameters)
