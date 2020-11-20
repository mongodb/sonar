from typing import List, Dict

from . import buildarg_from_dict

import docker


def docker_client():
    return docker.client.from_env()


def docker_build(
    path: str,
    dockerfile: str,
    tags: List[str] = None,
    buildargs: Dict[str, str] = None,
):
    """Builds docker images."""

    if tags is None:
        tags = []
    client = docker_client()

    import random

    # TODO(sonar): use something more appropriate
    image_name = "sonar-docker-build-{}".format(random.randint(1, 10000))

    # logging.info("Path: {}".format(path))
    # logging.info("dockerfile: {}".format(dockerfile))
    # logging.info("tag: {}".format(image_name))
    # logging.info("buildargs: {}".format(buildargs))

    buildargs_str = buildarg_from_dict(buildargs)

    # logging.info(
    #     "docker build {context} -f {dockerfile} {buildargs}".format(
    #         context=path, dockerfile=dockerfile, buildargs=buildargs_str
    #     )
    # )

    image, _ = client.images.build(
        path=path, dockerfile=dockerfile, tag=image_name, buildargs=buildargs
    )

    for tag in tags:
        registry, tag = tag.split(":")
        image.tag(registry, tag=tag)

        client.images.push(registry, tag=tag)
