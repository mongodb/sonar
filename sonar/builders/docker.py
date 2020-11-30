from typing import List, Dict
import logging
import random

import docker
from . import buildarg_from_dict


def docker_client():
    return docker.client.from_env()


def docker_build(
    path: str,
    dockerfile: str,
    tags: List[str] = None,
    buildargs: Dict[str, str] = None,
):
    if tags is None:
        tags = []

    client = docker_client()

    image_name = "sonar-docker-build-{}".format(random.randint(1, 10000))

    logging.debug("Path: {}".format(path))
    logging.debug("dockerfile: {}".format(dockerfile))
    logging.debug("tag: {}".format(image_name))
    logging.debug("buildargs: {}".format(buildargs))

    buildargs_str = buildarg_from_dict(buildargs)

    logging.debug(
        "docker build {context} -f {dockerfile} {buildargs}".format(
            context=path, dockerfile=dockerfile, buildargs=buildargs_str
        )
    )

    image, _ = client.images.build(
        path=path, dockerfile=dockerfile, tag=image_name, buildargs=buildargs
    )

    for tag in tags:
        registry, tag = tag.rsplit(":", 1)
        image.tag(registry, tag=tag)

        client.images.push(registry, tag=tag)


def docker_pull(
    image: str,
    tag: str,
):
    client = docker_client()

    return client.images.pull(image, tag=tag)


def docker_tag(
    image: docker.models.images.Image,
    registry: str,
    tag: str,
):
    image.tag(registry, tag)


def docker_push(registry: str, tag: str):
    client = docker_client()
    client.images.push(registry, tag=tag)
