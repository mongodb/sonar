from pytest import fixture

from sonar.sonar import process_image

from unittest.mock import patch, mock_open


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
