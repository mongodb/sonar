import logging
from unittest.mock import Mock, patch

from sonar.sonar import create_ecr_repository, is_valid_ecr_repo, process_image


@patch("sonar.sonar.find_inventory", return_value={"images": {"name": "image-name"}})
@patch("sonar.sonar.find_image", return_value={"name": "image-name"})
def test_specific_inventory(patched_find_image, patched_find_inventory):
    process_image(
        image_name="image-name",
        skip_tags=[],
        include_tags=[],
        pipeline=True,
        build_args={},
        inventory="other-inventory.yaml",
    )

    patched_find_image.assert_called_once_with("image-name", "other-inventory.yaml")
    patched_find_inventory.assert_called_once_with("other-inventory.yaml")


def test_repo_is_not_ecr():
    repos = (
        "quay.io/some-org/some-repo",
        "scan.connect.redhat.com/ospid-10001000100-1000/some-repo",
        "docker.io/some-more",
        "1.dkr.ecr.us-east-1.amazonaws.com",  # needs bigger account number
        "1.dkr.ecr.us-east.amazonaws.com",  # zone is not defined
    )
    for repo in repos:
        assert is_valid_ecr_repo(repo) is False


def test_repo_is_ecr():
    repos = (
        "123456789012.dkr.ecr.eu-west-1.amazonaws.com/some-other-repo",
        "123456789012.dkr.ecr.us-east-1.amazonaws.com/something-else",
    )
    for repo in repos:
        assert is_valid_ecr_repo(repo)


@patch("sonar.sonar.boto3.client")
def test_create_ecr_repository_creates_repo_when_ecr_repo(patched_client: Mock):
    returned_client = Mock()
    patched_client.return_value = returned_client

    # repository with no tag
    create_ecr_repository(
        "123456789012.dkr.ecr.eu-west-1.amazonaws.com/some-other-repo",
    )
    patched_client.assert_called_once()
    returned_client.create_repository.assert_called_once_with(
        repositoryName="some-other-repo",
        imageTagMutability="MUTABLE",
        imageScanningConfiguration={"scanOnPush": False},
    )
    patched_client.reset_mock()

    # repository with a tag
    create_ecr_repository(
        "123456789012.dkr.ecr.eu-west-1.amazonaws.com/some-other-repo:some-tag",
    )
    patched_client.assert_called_once()
    returned_client.create_repository.assert_called_once_with(
        repositoryName="some-other-repo",
        imageTagMutability="MUTABLE",
        imageScanningConfiguration={"scanOnPush": False},
    )


@patch("sonar.sonar.boto3.client")
def test_create_ecr_repository_doesnt_create_repo_when_not_ecr_repo(
    patched_client: Mock,
):
    returned_client = Mock()
    patched_client.return_value = returned_client

    create_ecr_repository(
        "my-private-repo.com/something",
    )
    patched_client.assert_not_called()
