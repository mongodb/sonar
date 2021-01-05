import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from urllib.request import urlretrieve
import uuid
from dataclasses import dataclass, field
from shutil import copyfile
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import boto3
import click
import yaml

from sonar.builders.docker import docker_build, docker_pull, docker_push, docker_tag
from sonar.template import render

LOGLEVEL = os.environ.get("LOGLEVEL", "WARNING").upper()
logging.basicConfig(level=LOGLEVEL)


@dataclass
class Context:
    inventory: Dict[str, str]
    image: Dict[str, str]

    # Store parameters passed as arguments
    parameters: Dict[str, str]

    skip_tags: Dict[str, str] = None
    include_tags: Dict[str, str] = None

    stage: Dict[str, str] = None

    # Defines if running in pipeline mode, this is, the output
    # is supposed to be consumable by the system calling sonar.
    pipeline: bool = False
    output: dict = field(default_factory=dict)

    # Generates a version_id to use if one is not present
    stored_version_id: str = str(uuid.uuid4())

    def I(self, string):
        return interpolate_vars(self, string, stage=self.stage)

    @property
    def image_name(self):
        return self.image["name"]

    @property
    def version_id(self):
        """Returns the version_id for this run.

        In evergreen context, it corresponds to Evergreen's run version_id, locally
        a uuid is used as a way of having independent builds.
        """
        return os.environ.get("version_id", self.stored_version_id)


def find_inventory(inventory: Optional[str] = None):
    if inventory is None:
        inventory = "inventory.yaml"

    with open(inventory, "r") as f:
        return yaml.safe_load(f)


def find_image(image_name: str, inventory: str):
    for image in find_inventory(inventory)["images"]:
        if image["name"] == image_name:
            return image

    raise ValueError("Image {} not found".format(image_name))


def build_dockerfile(image_from: str, statements: List[str]):
    dockerfile = "FROM {image_from}\n".format(image_from)

    for stmt in statements:
        dockerfile += stmt + "\n"

    return dockerfile


def find_variables_to_interpolate(string) -> List[str]:
    var_finder_re = r"\$\(inputs\.params\.(?P<var>\w+)\)"
    return re.findall(var_finder_re, string, re.UNICODE)


def find_variable_replacement(ctx: Context, variable, stage=None) -> str:
    if variable == "version_id":
        return ctx.version_id

    replacement = None
    # Find variable value on top level file
    if "vars" in ctx.inventory:
        if variable in ctx.inventory["vars"]:
            replacement = ctx.inventory["vars"][variable]

    # Find top-level defined variables overrides,
    # these might not be defined anywhere in the inventory file.
    # maybe they should?
    if variable in ctx.parameters:
        replacement = ctx.parameters[variable]

    # Find variable value on image
    if "vars" in ctx.image:
        if variable in ctx.image["vars"]:
            replacement = ctx.image["vars"][variable]

    # Find variables in stage
    if stage is not None and "vars" in stage:
        if variable in stage["vars"]:
            replacement = stage["vars"][variable]

    # Find variable values on cli parameters
    if "inputs" in ctx.image:
        if variable in ctx.image["inputs"]:
            # If in inputs then we get it form the parameters
            replacement = ctx.parameters[variable]

    return replacement


def find_variable_replacements(ctx, variables, stage=None) -> Dict[str, str]:
    replacements = {}
    for variable in variables:
        value = find_variable_replacement(ctx, variable, stage)
        if value is None:
            raise ValueError("No value for variable {}".format(variable))

        replacements[variable] = value

    return replacements


def interpolate_vars(ctx, string, stage=None) -> str:
    variables = find_variables_to_interpolate(string)
    replacements = find_variable_replacements(ctx, variables, stage)

    for variable in variables:
        string = string.replace(
            "$(inputs.params.{})".format(variable), replacements[variable]
        )

    return string


def build_add_statement(ctx, block) -> str:
    stmt = "ADD "
    if "from" in block:
        stmt += "--from={} ".format(block["from"])

    src = ctx.I(block["src"])
    dst = ctx.I(block["dst"])
    stmt += "{} {}\n".format(src, dst)

    return stmt


def find_docker_context(ctx: Context):
    if ctx.stage is not None:
        if "vars" in ctx.stage and "context" in ctx.stage["vars"]:
            return ctx.stage["vars"]["context"]

        if "dockercontext" in ctx.stage:
            return ctx.stage["dockercontext"]

    if "vars" in ctx.image and "context" in ctx.image["vars"]:
        return ctx.image["vars"]["context"]

    raise ValueError("No context defined for image or stage")


def should_skip_stage(stage: Dict[str, str], skip_tags: List[str]) -> bool:
    """Checks if this stage should be skipped."""
    stage_tags = stage.get("tags", [])
    if len(stage_tags) == 0:
        return False

    return not set(stage_tags).isdisjoint(skip_tags)


def should_include_stage(stage: Dict[str, str], include_tags: List[str]) -> bool:
    """Checks if this stage should be included in the run. If tags is empty,
    then all stages should be run, included this one."""
    stage_tags = stage.get("tags", [])
    if len(include_tags) == 0:
        # We don't have "include_tags" so all tasks should run
        return True

    return not set(stage_tags).isdisjoint(include_tags)


def task_dockerfile_create(ctx: Context):
    """Writes a simple Dockerfile from SCRATCH and ADD statements. This
    is intended to build a 'context' Dockerfile, this is, a Dockerfile that's
    not runnable but contains data.

    DEPRECATED: Use dockerfile_template or docker_build instead.
    """
    docker_context = find_docker_context(ctx)

    output_dockerfile = ctx.I(ctx.stage["output"][0]["dockerfile"])
    fro = ctx.stage.get("from", "scratch")
    with open("{}".format(output_dockerfile), "w") as fd:
        fd.write("FROM {}\n".format(fro))
        for f in ctx.stage["static_files"]:
            fd.write(build_add_statement(ctx, f))

    echo(ctx, "dockerfile-save-location", output_dockerfile)


def task_tag_image(ctx: Context):
    """
    Pulls an image from source and pushes into destination.
    """
    registry = ctx.I(ctx.stage["source"]["registry"])
    tag = ctx.I(ctx.stage["source"]["tag"])

    image = docker_pull(registry, tag)

    for output in ctx.stage["destination"]:
        registry = ctx.I(output["registry"])
        tag = ctx.I(output["tag"])
        echo(
            ctx,
            "docker-image-push",
            "{}:{}".format(registry, tag),
        )

        docker_tag(image, registry, tag)
        create_ecr_repository([registry])
        docker_push(registry, tag)


def get_rendering_params(ctx: Context):
    params = {}
    for param in ctx.stage["inputs"]:
        params[param] = find_variable_replacement(ctx, param, ctx.stage)

    return params


def run_dockerfile_template(ctx, dockerfile_context, distro):
    path = dockerfile_context
    params = get_rendering_params(ctx)

    logging.debug("rendering params are:")
    logging.debug(params)

    rendered = render(path, distro, params)
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write(rendered.encode("utf-8"))

    return tmp.name


def interpolate_buildargs(ctx, buildargs):
    copied_args = {}
    for k, v in buildargs.items():
        copied_args[k] = ctx.I(v)

    return copied_args


def create_ecr_repository(tags: List[str]):
    """
    creates ecr repository if it doesn't exist
    """
    client = boto3.client("ecr")

    for tag in tags:
        no_tag = tag.partition(":")[0]
        repository_name = no_tag.partition("/")[2]

        logging.info("Creating {}".format(repository_name))

        try:
            client.create_repository(
                repositoryName=repository_name,
                imageTagMutability="IMMUTABLE",
                imageScanningConfiguration={"scanOnPush": False},
            )
        except client.exceptions.RepositoryAlreadyExistsException:
            pass


def echo(ctx, entry_name, message, fg="white"):
    """Echoes a message"""

    err = ctx.pipeline
    section = ctx.output

    if ctx.pipeline:
        image_name = ctx.image["name"]
        if image_name not in ctx.output:
            ctx.output[image_name] = {}
        section = ctx.output[image_name]

        if ctx.stage is not None:
            stage_name = ctx.stage["name"]
            if stage_name not in ctx.output[image_name]:
                ctx.output[image_name][stage_name] = {}
            section = ctx.output[image_name][stage_name]

        section[entry_name] = message

    stage_title = ""
    if ctx.stage:
        stage_type = ctx.stage["task_type"]
        stage_name = ctx.stage["name"]
        task_title = "[{}/{}] ".format(stage_name, stage_type)

    # If --pipeline, these messages go to stderr
    click.secho("{}{}: {}".format(
        stage_title, entry_name, message), fg=fg, err=err)


def find_dockerfile(dockerfile: str):
    """Returns a Dockerfile file location that can be local or remote. If remote it
    will be downloaded into a temporary location first."""

    if dockerfile.startswith("https://"):
        tmpfile = tempfile.NamedTemporaryFile(delete=False)
        urlretrieve(dockerfile, tmpfile.name)

        return tmpfile.name

    return dockerfile


def task_docker_build(ctx: Context):
    name = ctx.stage["name"]
    docker_context = find_docker_context(ctx)

    dockerfile = find_dockerfile(ctx.I(ctx.stage["dockerfile"]))

    buildargs = interpolate_buildargs(ctx, ctx.stage.get("buildargs", {}))

    image = docker_build(docker_context, dockerfile, buildargs)

    for output in ctx.stage["output"]:
        registry = ctx.I(output["registry"])
        tag = ctx.I(output["tag"])

        echo(ctx, "docker-image-push", "{}:{}".format(registry, tag))
        docker_tag(image, registry, tag)
        create_ecr_repository([registry])
        docker_push(registry, tag)


def task_dockerfile_template(ctx: Context):
    name = ctx.stage["name"]

    docker_context = find_docker_context(ctx)
    template_context = docker_context

    try:
        template_context = ctx.image["vars"]["template_context"]
    except KeyError:
        pass

    dockerfile = run_dockerfile_template(
        ctx, template_context, ctx.stage.get("distro"))

    for output in ctx.stage["output"]:
        if "dockerfile" in output:
            output_dockerfile = ctx.I(output["dockerfile"])
            copyfile(dockerfile, output_dockerfile)

            echo(ctx, "dockerfile-save-location", output_dockerfile)


def find_skip_tags(params: Optional[Dict[str, str]] = None) -> List[str]:
    """Returns a list of tags passed in params that should be excluded from the build."""
    if params is None:
        params = {}

    tags = params.get("skip_tags", [])

    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t != ""]

    return tags


def find_include_tags(params: Optional[Dict[str, str]] = None) -> List[str]:
    """Returns a list of tags passed in params that should be included in the build."""
    if params is None:
        params = {}

    tags = params.get("include_tags", [])

    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t != ""]

    return tags


def process_image(
    image_name: str,
    skip_tags: Union[str, List[str]],
    include_tags: Union[str, List[str]],
    pipeline: bool = True,
    build_args: Optional[Dict[str, str]] = None,
    inventory: Optional[str] = None,
):
    if build_args is None:
        build_args = {}

    ctx = build_context(image_name, skip_tags,
                        include_tags, build_args, inventory)
    ctx.pipeline = pipeline

    echo(ctx, "image_build_start", image_name, fg="yellow")

    for idx, stage in enumerate(ctx.image.get("stages", [])):
        ctx.stage = stage
        name = ctx.stage["name"]
        if should_skip_stage(stage, ctx.skip_tags):
            echo(ctx, "skipping-stage", name, fg="green")
            continue

        if not should_include_stage(stage, ctx.include_tags):
            echo(ctx, "skipping-stage", name, fg="green")
            continue

        echo(
            ctx,
            "stage-started {}".format(stage["name"]),
            "{}/{}".format(idx + 1, len(ctx.image["stages"])),
        )

        if stage["task_type"] == "dockerfile_create":
            task_dockerfile_create(ctx)
        elif stage["task_type"] == "dockerfile_template":
            task_dockerfile_template(ctx)
        elif stage["task_type"] == "docker_build":
            task_docker_build(ctx)
        elif stage["task_type"] == "tag_image":
            task_tag_image(ctx)
        else:
            raise NotImplementedError(
                "task_type {} not supported".format(stage["task_type"])
            )

    if ctx.pipeline:
        return ctx.output


def make_list_of_str(value: Union[None, str, List[str]]) -> List[str]:
    if value is None:
        return []

    if isinstance(value, str):
        if len(value) == 0:
            return []

        return [e.strip() for e in value.split(",") if e != ""]

    return value


def build_context(
    image_name: str,
    skip_tags: Union[str, List[str]],
    include_tags: Union[str, List[str]],
    build_args: Optional[Dict[str, str]] = None,
    inventory: Optional[str] = None,
) -> Context:
    """A Context includes the whole inventory, the image to build, the current stage,
    and the `I` interpolation function."""
    image = find_image(image_name, inventory)

    build_args = build_args.copy()
    logging.debug("Should skip tags {}".format(skip_tags))

    return Context(
        inventory=find_inventory(inventory),
        image=image,
        parameters=build_args,
        skip_tags=make_list_of_str(skip_tags),
        include_tags=make_list_of_str(include_tags),
    )
