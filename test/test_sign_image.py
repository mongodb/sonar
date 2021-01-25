from sonar.sonar import process_image, is_signing_enabled

import pytest
import os
import os.path
from pathlib import Path
from unittest.mock import patch, mock_open, call
from sonar import DCT_ENV_VARIABLE, DCT_PASSPHRASE


@pytest.fixture()
def ys7():
    return open("test/yaml_scenario7.yaml").read()


@patch("sonar.sonar.get_secret", return_value="SECRET")
@patch("sonar.sonar.get_private_key_id", return_value="abc.key")
@patch("sonar.sonar.clear_signing_environment")
@patch("sonar.sonar.docker_push")
@patch("sonar.sonar.docker_tag")
@patch("sonar.sonar.docker_build")
@patch("sonar.sonar.urlretrieve")
@patch("sonar.sonar.create_ecr_repository")
def test_sign_image(
    patched_create_ecr_repository,
    patched_urlretrive,
    patched_docker_build,
    patched_docker_tag,
    patched_docker_push,
    patched_clear_signing_environment,
    patched_get_private_key_id,
    patched_get_secret,
    ys7,
):
    with patch("builtins.open", mock_open(read_data=ys7)) as mock_file:
        pipeline = process_image(
            image_name="image0",
            skip_tags=[],
            include_tags=[],
            pipeline=True,
            build_args={},
        )

    patched_clear_signing_environment.assert_called_once_with("abc.key")
    assert os.environ.get(DCT_ENV_VARIABLE, "0") == "1"
    assert os.environ.get(DCT_PASSPHRASE, "0") == "SECRET"

    secret_calls = [
        call("test/kube/passphrase", "us-east-1"),
        call("test/kube/secret", "us-east-1"),
    ]

    patched_get_secret.assert_has_calls(secret_calls)
    patched_get_private_key_id.assert_called_once_with("foo", "evergreen_ci")


def test_is_signing_enabled():
    test_cases = [
        {
            "input": {
                "signer_name": "foo",
                "key_secret_name": "key_name",
                "passphrase_secret_name": "pass_name",
                "region": "us-east-1",
            },
            "result": True,
        },
        {
            "input": {
                "key_secret_name": "key_name",
                "passphrase_secret_name": "pass_name",
                "region": "us-east-1",
            },
            "result": False,
        },
        {
            "input": {
                "signer_name": "foo",
                "passphrase_secret_name": "pass_name",
                "region": "us-east-1",
            },
            "result": False,
        },
        {
            "input": {
                "signer_name": "foo",
                "key_secret_name": "key_name",
                "region": "us-east-1",
            },
            "result": False,
        },
        {
            "input": {
                "signer_name": "foo",
                "key_secret_name": "key_name",
                "passphrase_secret_name": "pass_name",
            },
            "result": False,
        },
    ]

    for case in test_cases:
        assert is_signing_enabled(case["input"]) == case["result"]
