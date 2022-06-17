import logging
import random
import subprocess
from typing import Dict, Optional

import docker
import docker.errors

from . import SonarAPIError, SonarBuildError, buildarg_from_dict, labels_from_dict


def docker_client() -> docker.DockerClient:
    return docker.client.from_env(timeout=60 * 60 * 24)


def docker_build(
        path: str,
        dockerfile: str,
        buildargs: Optional[Dict[str, str]] = None,
        labels: Optional[Dict[str, str]] = None,
        platform: Optional[str] = None,
):
    """Builds a docker image."""
    logger = logging.getLogger(__name__)

    image_name = "sonar-docker-build-{}".format(random.randint(1, 10000))

    logger.info("path: {}".format(path))
    logger.info("dockerfile: {}".format(dockerfile))
    logger.info("tag: {}".format(image_name))
    logger.info("buildargs: {}".format(buildargs))
    logger.info("labels: {}".format(labels))

    try:
        # docker build from docker-py has bugs resulting in errors or invalid platform when building with specified --platform=linux/amd64 on M1
        docker_build_cli(
            logger=logger, path=path, dockerfile=dockerfile, tag=image_name, buildargs=buildargs, labels=labels, platform=platform,
        )

        client = docker_client()
        return client.images.get(image_name)
    except docker.errors.APIError as e:
        raise SonarAPIError from e


def _get_build_log(e: docker.errors.BuildError) -> str:
    build_logs = "\n"
    for item in e.build_log:
        if "stream" not in item:
            continue
        item_str = item["stream"]
        build_logs += item_str
    return build_logs


def docker_build_cli(
        logger: logging.Logger,
        path: str, dockerfile: str,
        tag: str,
        buildargs: Optional[Dict[str, str]],
        labels=Optional[Dict[str, str]],
        platform=Optional[str]
):
    dockerfile_path = dockerfile
    # if dockerfile is relative it has to be set as relative to context (path)
    if not dockerfile_path.startswith('/'):
        dockerfile_path = f"{path}/{dockerfile_path}"

    args = get_docker_build_cli_args(path=path, dockerfile=dockerfile_path, tag=tag, buildargs=buildargs, labels=labels, platform=platform)

    args_str = " ".join(args)
    logger.info(f"executing cli docker build: {args_str}")

    cp = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if cp.returncode != 0:
        raise SonarAPIError(cp.stderr)


def get_docker_build_cli_args(
        path: str,
        dockerfile: str,
        tag: str,
        buildargs: Optional[Dict[str, str]],
        labels=Optional[Dict[str, str]],
        platform=Optional[str]
):
    args = ["docker", "buildx", "build", "--progress", "plain", path, "-f", dockerfile, "-t", tag]
    if buildargs is not None:
        for k, v in buildargs.items():
            args.append("--build-arg")
            args.append(f"{k}={v}")

    if labels is not None:
        for k, v in labels.items():
            args.append("--label")
            args.append(f"{k}={v}")

    if platform is not None:
        args.append("--platform")
        args.append(platform)

    return args


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
    def inner_docker_push(should_raise=False):

        # We can't use docker-py here
        # as it doesn't support DOCKER_CONTENT_TRUST
        # env variable, which could be needed
        cp = subprocess.run(
            ["docker", "push", f"{registry}:{tag}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if cp.returncode != 0:
            if should_raise:
                raise SonarAPIError(cp.stderr)

            return False

        return True

    retries = 3
    while retries >= 0:
        if inner_docker_push(retries == 0):
            break
        retries -= 1
