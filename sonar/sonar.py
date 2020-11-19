#!/usr/bin/env python3

from dataclasses import dataclass, field
import argparse
import json
import logging
import re
import os
from shutil import copyfile
import subprocess
import sys
import tempfile
import yaml
import uuid

import boto3
import click
import docker
import git

from typing import List, Dict, Callable, Union

from sonar.template import render

"""
Sonar takes a definition of an image building process and
builds Docker images in parallel and publish them to a given
repo/destination.

It has the concept of stages an each stage has a different set of
images and destination repos where to push them.

A given stage can pick images from a previous image and move them
to a differnet repo.

"""

LOGLEVEL = os.environ.get("LOGLEVEL", "WARNING").upper()
logging.basicConfig(level=LOGLEVEL)


@dataclass
class Builder:
    build: Callable[[str, str, str, str, Dict[str, str]], None]


@dataclass
class Context:
    inventory: Dict[str, str]
    image: Dict[str, str]

    # Store parameters passed as arguments
    parameters: Dict[str, str]
    builder: Builder

    skip_tags: Dict[str, str] = None

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


def inventory():
    try:
        fd = open("inventory.yaml")
    except FileNotFoundError:
        fd = open("sonar/inventory.yaml")
    return yaml.safe_load(fd)


def find_image(image_name: str):
    for image in inventory()["images"]:
        if image["name"] == image_name:
            return image

    raise ValueError("Image {} not found".format(image_name))


def build_dockerfile(image_from: str, statements: List[str]):
    dockerfile = "FROM {image_from}\n".format(image_from)

    for stmt in statements:
        dockerfile += stmt + "\n"

    return dockerfile


def find_variables_to_interpolate(string) -> List[str]:
    var_finder_re = r"\$\(inputs\.params\.(?P<var>[a-z0-9_]*)\)"
    return re.findall(var_finder_re, string)


def find_variable_replacement(ctx: Context, variable, stage=None) -> str:
    if variable == "version_id":
        return ctx.version_id

    replacement = None
    # Find variable value on top level file
    if "vars" in ctx.inventory:
        if variable in ctx.inventory["vars"]:
            replacement = ctx.inventory["vars"][variable]

    # Find top-level defined variables overrides
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


def args_to_dict(parameters) -> Dict[str, str]:
    if parameters is None:
        return {}

    d = {}

    for p in parameters:
        entry = p[0].split("=")
        d[entry[0]] = entry[1]

    return d


def run_stage_script(ctx):
    if "script" not in ctx.stage:
        raise ValueError("Stage should contain a 'script' attribute.")

    echo(ctx, "execute-script", ctx.stage["script"])
    output = subprocess.run(ctx.stage["script"], check=True, stdout=subprocess.PIPE)

    echo(ctx, "script-output", output.stdout.decode("utf-8"))


def docker_client():
    return docker.client.from_env()


def find_docker_context(ctx: Context):
    if ctx.stage is not None:
        if "vars" in ctx.stage and "context" in ctx.stage["vars"]:
            return ctx.stage["vars"]["context"]

        if "dockercontext" in ctx.stage:
            return ctx.stage["dockercontext"]

    if "vars" in ctx.image and "context" in ctx.image["vars"]:
        return ctx.image["vars"]["context"]

    raise ValueError("No context defined for image or stage")


def task_script_runner(ctx: Context):
    # Run before "building" the image
    run_stage_script(ctx)


def should_skip_stage(stage: Dict[str, str], tags: List[str]) -> bool:
    if "tags" not in stage:
        return False

    return not set(stage["tags"]).isdisjoint(set(tags))


def task_dockerfile_create(ctx: Context):
    """Writes a simple Dockerfile from SCRATCH and a bunch of ADD statements. This
    is intended to build a 'context' Dockerfile, this is, a Dockerfile that's
    not runnable but contains data.

    """
    docker_context = find_docker_context(ctx)

    output_dockerfile = ctx.I(ctx.stage["output"][0]["dockerfile"])
    fro = ctx.stage.get("from", "scratch")
    with open("{}".format(output_dockerfile), "w") as fd:
        fd.write("FROM {}\n".format(fro))
        for f in ctx.stage["static_files"]:
            fd.write(build_add_statement(ctx, f))

    echo(ctx, "dockerfile-save-location", output_dockerfile)


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


def buildarg_from_dict(args):
    if args is None:
        return ""

    return " ".join(["--build-arg {}={}".format(k, v) for k, v in args.items()])


def podman_buildid_from_subprocess_run(result) -> str:
    return result.stdout.decode("utf-8").split("\n")[-1]


def podman_build(
    path: str,
    dockerfile: str,
    tags: List[str],
    buildargs: Dict[str, str] = None,
):
    buildargs_str = buildarg_from_dict(buildargs)
    build_command = f"podman build {path} -f {dockerfile} {buildargs_str}"
    logging.info(build_command)

    result = subprocess.run(build_command.split(), capture_output=True, check=True)
    buildid = podman_buildid_from_subprocess_run(result)

    for tag in tags:
        tag_command = f"podman tag {buildid} {tag}".split()
        subprocess.run(tag_command, check=True)

        push_command = f"podman push {buildid} {tag}"
        subprocess.run(push_command.split(), check=True)


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

    image, _ = client.images.build(
        path=path, dockerfile=dockerfile, tag=image_name, buildargs=buildargs
    )

    for tag in tags:
        registry, tag = tag.split(":")
        image.tag(registry, tag=tag)

        client.images.push(registry, tag=tag)


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
    click.secho("{}{}: {}".format(stage_title, entry_name, message), fg=fg, err=err)


def task_docker_build(ctx: Context):
    name = ctx.stage["name"]
    docker_context = find_docker_context(ctx)
    dockerfile = ctx.I(ctx.stage["dockerfile"])

    try:
        buildargs = interpolate_buildargs(ctx, ctx.stage.get("buildargs", {}))

        tags = []
        for output in ctx.stage["output"]:
            tag = "{}:{}".format(output["registry"], output["tag"])
            tags.append(ctx.I(tag))

        create_ecr_repository(tags)
        ctx.builder(docker_context, dockerfile, tags, buildargs)

        for tag in tags:
            echo(ctx, "docker-image-push", "{}".format(tag))

    except docker.errors.BuildError:
        echo(ctx, "error", "building image")
        raise


def task_dockerfile_template(ctx: Context):
    name = ctx.stage["name"]

    docker_context = find_docker_context(ctx)
    template_context = docker_context

    try:
        # Use a template_context for running dockerfile_generator.py in case
        # this is needed. This is relevant for multi-stage images that require
        # the full project to be built, so their docker_context is different
        # from the directory where dockerfile_generator should run.
        template_context = ctx.image["vars"]["template_context"]
    except KeyError:
        pass

    dockerfile = run_dockerfile_template(ctx, template_context, ctx.stage.get("distro"))

    # TODO: replace this with what we have in "push" entry (or output maybe).
    # push = ctx.I(ctx.stage["registry"])
    for output in ctx.stage["output"]:
        if "dockerfile" in output:
            output_dockerfile = ctx.I(output["dockerfile"])
            copyfile(dockerfile, output_dockerfile)

            echo(ctx, "dockerfile-save-location", output_dockerfile)


def find_skip_tags(params: Union[None, Dict[str, str]] = None) -> List[str]:
    if params is None:
        params = {}

    if "skip_tags" not in params:
        return

    skip_tags = params["skip_tags"]
    del params["skip_tags"]

    if isinstance(skip_tags, str):
        skip_tags = skip_tags.split(",")

    return skip_tags


def process(
    image_name: str,
    builder: str = "docker",
    pipeline: bool = True,
    build_args: Union[None, Dict[str, str]] = None,
):
    if build_args is None:
        build_args = {}

    ctx = build_context(image_name, builder, build_args)
    ctx.pipeline = pipeline

    echo(ctx, "image_build_start", image_name, fg="yellow")
    echo(ctx, "image_builder", builder, fg="yellow")

    for idx, stage in enumerate(ctx.image["stages"]):
        ctx.stage = stage
        name = ctx.stage["name"]
        if should_skip_stage(stage, ctx.skip_tags):
            echo(ctx, "skipping-task", name, fg="green")
            continue

        echo(
            ctx,
            "Stage started {}".format(stage["name"]),
            "{}/{}".format(idx + 1, len(ctx.image["stages"])),
        )

        if stage["task_type"] == "dockerfile_create":
            task_dockerfile_create(ctx)
        elif stage["task_type"] == "dockerfile_template":
            task_dockerfile_template(ctx)
        elif stage["task_type"] == "docker_build":
            task_docker_build(ctx)
        elif stage["task_type"] == "script_runner":
            task_script_runner(ctx)
        else:
            raise NotImplementedError(
                "task_type {} not supported".format(stage["task_type"])
            )

    if ctx.pipeline:
        return ctx.output
        # print(json.dumps(ctx.output, indent=2))


def get_project_root(path):
    repo = git.Repo(path, search_parent_directories=True)
    return repo.git.rev_parse("--show-toplevel")


def build_context(
    image_name: str,
    builder_name: str = "docker",
    build_args: Union[None, Dict[str, str]] = None,
) -> Context:
    """A Context includes the whole inventory, the image to build, the current stage,
    and the `I` interpolation function."""
    image = find_image(image_name)

    builder = None
    if builder_name == "docker":
        builder = docker_build
    elif builder_name == "podman":
        builder = podman_build
    else:
        raise ValueError("Builder '{}' not recognized".format(builder_name))

    build_args = build_args.copy()
    skip_tags = find_skip_tags(build_args)
    logging.debug("Should skip tags {}".format(skip_tags))

    return Context(
        inventory=inventory(),
        image=image,
        builder=builder,
        parameters=build_args,
        skip_tags=skip_tags,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image")
    parser.add_argument("-p", dest="parameters", nargs=1, action="append")
    parser.add_argument("--pipeline", default=False, action="store_true")
    parser.add_argument("--builder", default="docker", type=str)
    parser.add_argument("--skip_tags", default="", type=str)
    args = parser.parse_args()

    print(args)
    d = args_to_dict(args.parameters)

    cwd = os.getcwd()
    root = get_project_root(cwd)
    os.chdir(root)
    process(args.image, args.builder, args.pipeline, d)

    os.chdir(cwd)
