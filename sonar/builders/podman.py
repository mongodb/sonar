from typing import List, Dict

from . import buildarg_from_dict

import subprocess


def podman_build(
    path: str,
    dockerfile: str,
    tags: List[str],
    buildargs: Dict[str, str] = None,
):
    buildargs_str = buildarg_from_dict(buildargs)
    build_command = f"podman build {path} -f {dockerfile} {buildargs_str}"
    # logging.info(build_command)

    result = subprocess.run(build_command.split(), capture_output=True, check=True)
    buildid = podman_buildid_from_subprocess_run(result)

    for tag in tags:
        tag_command = f"podman tag {buildid} {tag}".split()
        subprocess.run(tag_command, check=True)

        push_command = f"podman push {buildid} {tag}"
        subprocess.run(push_command.split(), check=True)


def podman_buildid_from_subprocess_run(result) -> str:
    return result.stdout.decode("utf-8").split("\n")[-1]
