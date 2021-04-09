from sonar.sonar import (
    process_image,
    find_dockerfile,
)

from types import SimpleNamespace as sn

from unittest.mock import patch, mock_open, MagicMock, Mock


@patch("sonar.sonar.docker_push")
@patch("sonar.sonar.docker_tag")
@patch("sonar.sonar.docker_build")
@patch("sonar.sonar.urlretrieve")
@patch("sonar.sonar.create_ecr_repository")
def test_dockerfile_from_url(
    patched_docker_build,
    patched_docker_tag,
    patched_docker_push,
    patched_urlretrive,
    patched_create_ecr_repository,
):
    with open("test/yaml_scenario6.yaml") as fd:
        with patch("builtins.open", mock_open(read_data=fd.read())) as _mock_file:
            pipeline = process_image(
                image_name="image0",
                skip_tags=[],
                include_tags=["test_dockerfile_from_url"],
                build_args={},
            )

    patched_urlretrive.assert_called_once()
    patched_docker_build.assert_called_once()
    patched_docker_tag.assert_called_once()
    patched_docker_push.assert_called_once()
    patched_create_ecr_repository.assert_called_once()


@patch(
    "sonar.sonar.tempfile.NamedTemporaryFile", return_value=sn(name="random-filename")
)
@patch("sonar.sonar.urlretrieve")
def test_find_dockerfile_fetches_file_from_url(patched_urlretrieve, patched_tempfile):
    # If passed a dockerfile which starts with https://
    # make sure urlretrieve and NamedTemporaryFile is called
    dockerfile = find_dockerfile("https://something")

    patched_urlretrieve.assert_called_once()
    patched_tempfile.assert_called_once_with(delete=False)
    assert dockerfile == "random-filename"

    patched_urlretrieve.reset_mock()

    # If dockerfile is a localfile, urlretrieve should not be called.
    dockerfile = find_dockerfile("/localfile/somewhere")
    patched_urlretrieve.assert_not_called()
    assert dockerfile == "/localfile/somewhere"
