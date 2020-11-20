"""Used to be called with unit tests mostly."""

from typing import List, Dict


def noop_build(
    _path: str,
    _dockerfile: str,
    _tags: List[str] = None,
    _buildargs: Dict[str, str] = None,
):
    pass
