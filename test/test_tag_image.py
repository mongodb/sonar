from sonar.sonar import process_image

import pytest
from unittest.mock import patch, mock_open, call


@pytest.fixture()
def ys4():
    return open("test/yaml_scenario4.yaml").read()


@patch("sonar.sonar.docker_pull", return_value="123")
@patch("sonar.sonar.docker_tag")
@patch("sonar.sonar.docker_push")
def test_tag_image(patched_docker_push, patched_docker_tag, patched_docker_pull, ys4):
    with patch("builtins.open", mock_open(read_data=ys4)) as mock_file:
        pipeline = process_image(image_name="image0", pipeline=True, build_args={})

    patched_docker_pull.assert_called_once_with(
        "source-registry-0-test_value0", "source-tag-0-test_value1"
    )

    tag_calls = [
        call(
            "123", "dest-registry-0-test_value0", "dest-tag-0-test_value0-test_value1"
        ),
        call(
            "123", "dest-registry-1-test_value0", "dest-tag-1-test_value0-test_value1"
        ),
    ]
    patched_docker_tag.assert_has_calls(tag_calls)

    push_calls = [
        call("dest-registry-0-test_value0", "dest-tag-0-test_value0-test_value1"),
        call("dest-registry-1-test_value0", "dest-tag-1-test_value0-test_value1"),
    ]
    patched_docker_push.assert_has_calls(push_calls)
