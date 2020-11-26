from sonar.sonar import (
    find_include_tags,
    find_skip_tags,
    should_skip_stage,
    should_include_stage,
    build_context,
    process,
)

import pytest
from unittest.mock import patch, mock_open


@pytest.fixture()
def ys3():
    return open("test/yaml_scenario3.yaml").read()


def test_include_tags_empty_params():
    assert find_include_tags(None) == []
    assert find_include_tags({}) == []
    assert find_include_tags({"nop": 1}) == []


def test_include_tags_is_list():
    assert find_include_tags({"include_tags": ["1", "2"]}) == ["1", "2"]
    assert find_include_tags({"nop": 1, "include_tags": ["1", "2"]}) == ["1", "2"]


def test_include_tags_is_str():
    assert find_include_tags({"include_tags": ""}) == []
    assert find_include_tags({"include_tags": "1,2"}) == ["1", "2"]
    assert find_include_tags({"include_tags": "hi"}) == ["hi"]
    assert find_include_tags({"include_tags": "hi,"}) == ["hi"]


def test_skip_tags():
    assert find_skip_tags({"skip_tags": ""}) == []
    assert find_skip_tags(None) == []
    assert find_skip_tags({}) == []
    assert find_skip_tags({"nop": 1}) == []
    assert find_skip_tags({"nop": 1, "skip_tags": []}) == []

    assert find_skip_tags({"nop": 1, "skip_tags": ["1"]}) == ["1"]
    assert find_skip_tags({"nop": 1, "skip_tags": ["1", "2"]}) == ["1", "2"]

    assert find_skip_tags({"nop": 1, "skip_tags": "1"}) == ["1"]
    assert find_skip_tags({"nop": 1, "skip_tags": "1,2"}) == ["1", "2"]
    assert find_skip_tags({"nop": 1, "skip_tags": "1, 2"}) == ["1", "2"]
    assert find_skip_tags({"nop": 1, "skip_tags": "1, 2,"}) == ["1", "2"]


def test_should_include_stage():
    assert should_include_stage({"tags": ["a", "b"]}, [])
    assert should_include_stage({"tags": ["a", "b"]}, ["a"])
    assert should_include_stage({"tags": ["a", "b"]}, ["b"])
    assert should_include_stage({"tags": ["a", "b"]}, ["a", "b"])
    assert should_include_stage({"tags": ["a", "b"]}, ["b", "a"])

    assert should_include_stage({"tags": ["a", "b"]}, ["a", "c"])
    assert should_include_stage({"tags": ["a", "b"]}, ["b", "c"])

    assert not should_include_stage({"tags": ["a", "b"]}, ["c"])
    assert not should_include_stage({"tags": ["b"]}, ["c"])
    assert not should_include_stage({"tags": []}, ["c"])


def test_should_skip_stage():
    assert should_skip_stage({"tags": ["a", "b"]}, ["a"])
    assert should_skip_stage({"tags": ["a", "b"]}, ["a", "b"])
    assert should_skip_stage({"tags": ["a", "b"]}, ["a", "b", "c"])

    assert not should_skip_stage({"tags": []}, [])
    assert not should_skip_stage({"tags": []}, ["a"])
    assert not should_skip_stage({"tags": []}, ["a", "b"])
    assert not should_skip_stage({"tags": ["a"]}, ["b"])
    assert not should_skip_stage({"tags": ["a", "b"]}, [])
    assert not should_skip_stage({"tags": ["a", "b"]}, ["c"])


def test_include_tags(ys3):
    """Only includes the stage with the corresponding tag."""
    build_args = {"include_tags": ["tag0"]}
    with patch("builtins.open", mock_open(read_data=ys3)) as mock_file:
        pipeline = process(
            image_name="image0", builder="noop", pipeline=True, build_args=build_args
        )

    assert "skipping-stage" not in pipeline["image0"]["stage0"]
    assert pipeline["image0"]["stage1"] == {"skipping-stage": "stage1"}


def test_include_tags(ys3):
    """Only includes the stage with the corresponding tag."""
    build_args = {"include_tags": ["tag0", "tag1"]}
    with patch("builtins.open", mock_open(read_data=ys3)) as mock_file:
        pipeline = process(
            image_name="image0", builder="noop", pipeline=True, build_args=build_args
        )

    assert "skipping-stage" not in pipeline["image0"]["stage0"]
    assert "skipping-stage" not in pipeline["image0"]["stage1"]


def test_skip_tags(ys3):
    """Only includes the stage with the corresponding tag."""
    build_args = {"skip_tags": ["tag0"]}
    with patch("builtins.open", mock_open(read_data=ys3)) as mock_file:
        pipeline = process(
            image_name="image0", builder="noop", pipeline=True, build_args=build_args
        )

    assert pipeline["image0"]["stage0"] == {"skipping-stage": "stage0"}
    assert "skipping-stage" not in pipeline["image0"]["stage1"]


def test_skip_tags(ys3):
    """Only includes the stage with the corresponding tag."""
    build_args = {"skip_tags": ["tag0", "tag1"]}
    with patch("builtins.open", mock_open(read_data=ys3)) as mock_file:
        pipeline = process(
            image_name="image0", builder="noop", pipeline=True, build_args=build_args
        )

    assert pipeline["image0"]["stage0"] == {"skipping-stage": "stage0"}
    assert pipeline["image0"]["stage1"] == {"skipping-stage": "stage1"}


def test_skip_include_tags(ys3):
    """Only includes the stage with the corresponding tag."""
    build_args = {"skip_tags": ["tag0"], "include_tags": ["tag1"]}
    with patch("builtins.open", mock_open(read_data=ys3)) as mock_file:
        pipeline = process(
            image_name="image0", builder="noop", pipeline=True, build_args=build_args
        )

    assert pipeline["image0"]["stage0"] == {"skipping-stage": "stage0"}
    assert "skipping-stage" not in pipeline["image0"]["stage1"]
