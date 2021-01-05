from typing import List, Dict, Optional
import logging
import random

import docker
from . import (
    buildarg_from_dict,
    SonarBuildError,
    SonarAPIError,
)


def docker_client() -> docker.DockerClient:
    return docker.client.from_env(timeout=60*60*24)


def docker_build(
    path: str,
    dockerfile: str,
    buildargs: Optional[Dict[str, str]] = None,
):
    """Builds a docker image."""
    client = docker_client()

    image_name = "sonar-docker-build-{}".format(random.randint(1, 10000))

    logging.info("Path: {}".format(path))
    logging.info("dockerfile: {}".format(dockerfile))
    logging.info("tag: {}".format(image_name))
    logging.info("buildargs: {}".format(buildargs))

    buildargs_str = buildarg_from_dict(buildargs)

    logging.info(
        "docker build {context} -f {dockerfile} {buildargs}".format(
            context=path, dockerfile=dockerfile, buildargs=buildargs_str
        )
    )

    try:
        image, _ = client.images.build(
            path=path, dockerfile=dockerfile, tag=image_name, buildargs=buildargs
        )
        return image
    except (docker.errors.BuildError) as e:
        raise SonarBuildError from e

    except (docker.errors.APIError) as e:
        raise SonarAPIError from e


def docker_pull(
    image: str,
    tag: str,
):
    client = docker_client()

    try:
        return client.images.pull(image, tag=tag)
    except docker.errors.APIError as e:
        raise SonarAPIError from e


def docker_tag(
    image: docker.models.images.Image,
    registry: str,
    tag: str,
):
    try:
        return image.tag(registry, tag)
    except docker.errors.APIError as e:
        raise SonarAPIError from e


def docker_push(registry: str, tag: str):
    client = docker_client()

    try:
        resp = client.images.push(registry, tag=tag, stream=True, decode=True)

        for res in resp:
            if "error" in res:
                raise SonarAPIError(res["error"])

    except docker.errors.APIError as e:
        raise SonarAPIError from e
