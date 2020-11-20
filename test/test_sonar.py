from pytest import fixture

from sonar.sonar import process

from unittest.mock import patch, mock_open


def test_yaml_reading():
    yaml_scenario0 = open("test/yaml_scenario0.yaml").read()
    with patch("builtins.open", mock_open(read_data=yaml_scenario0)) as mock_file:
        result = process("image0", "noop")
