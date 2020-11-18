from unittest import mock

from sonar import (
    find_skip_tags,
    should_skip_stage,
)


def test_sonnary():
    assert True


def test_skip_tags():
    params = {
        "some": "thing",
        "skip_tags": "ubi,rhel",
    }

    tags = find_skip_tags(params)
    assert len(tags) == 2
    assert tags[0] == "ubi"
    assert tags[1] == "rhel"
    assert "skip_tags" not in params

    tags = find_skip_tags()
    assert tags is None

    params = {
        "some": "thing",
        "skip_tags": "ubi",
    }

    tags = find_skip_tags(params)
    assert len(tags) == 1
    assert tags[0] == "ubi"
    assert "skip_tags" not in params
    assert "some" in params


def test_should_skip_tags():
    stage = {
        "name": "something",
        "tags": ["tag0", "tag1"],
    }

    assert should_skip_stage(stage, ["tag0"])
    assert should_skip_stage(stage, ["tag1"])
    assert not should_skip_stage(stage, ["another-tag"])

    stage = {
        "name": "something",
    }
    assert not should_skip_stage(stage, ["tag0"])

    stage = {
        "name": "something",
        "tags": ["ubi"],
    }

    assert not should_skip_stage(stage, ["ubuntu"])
