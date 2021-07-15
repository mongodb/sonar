from typing import List, Dict, Optional
import logging
import random
import os

import docker
from . import (
    buildarg_from_dict,
    SonarBuildError,
    SonarAPIError, labels_from_dict,
)
import subprocess


def docker_client() -> docker.DockerClient:
    return docker.client.from_env(timeout=60 * 60 * 24)


def docker_build(
    path: str,
    dockerfile: str,
    buildargs: Optional[Dict[str, str]] = None,
    labels: Optional[Dict[str, str]] = None,
):
    """Builds a docker image."""
    client = docker_client()

    logger = logging.getLogger(__name__)

    image_name = "sonar-docker-build-{}".format(random.randint(1, 10000))

    logger.info("Path: {}".format(path))
    logger.info("dockerfile: {}".format(dockerfile))
    logger.info("tag: {}".format(image_name))
    logger.info("buildargs: {}".format(buildargs))
    logger.info("labels: {}".format(labels))

    buildargs_str = buildarg_from_dict(buildargs)
    labels_str = labels_from_dict(labels)

    logger.info(
        "docker build {context} -f {dockerfile} {buildargs} {labels}".format(
            context=path, dockerfile=dockerfile, buildargs=buildargs_str, labels=labels_str,
        )
    )

    try:
        image, _ = client.images.build(
            path=path, dockerfile=dockerfile, tag=image_name, buildargs=buildargs, labels=labels,
        )
        return image
    except (docker.errors.BuildError) as e:
        raise SonarBuildError(_get_build_log(e)) from e

    except (docker.errors.APIError) as e:
        raise SonarBuildError from e


def _get_build_log(e: docker.errors.BuildError) -> str:
    build_logs = "\n"
    for item in e.build_log:
        if "stream" not in item:
            continue
        item_str = item["stream"]
        build_logs += item_str
    return build_logs


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
    # We can't use docker-py here
    # as it doesn't support DOCKER_CONTENT_TRUST
    # env variable, which could be needed
    cp = subprocess.run(
        ["docker", "push", f"{registry}:{tag}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if cp.returncode != 0:
        raise SonarAPIError(cp.stderr)
