import pytest

from poc.config import ConfigurationError
from scripts.test_gemini_live import _validate_args, build_parser


def _parse(*arguments):
    return build_parser().parse_args(list(arguments))


def test_device_argument_is_parsed_and_validated():
    args = _parse("--input", "mic", "--device", "2")
    _validate_args(args)
    assert args.device == 2


def test_negative_device_is_rejected():
    args = _parse("--input", "mic", "--device", "-1")
    with pytest.raises(ConfigurationError, match="--device"):
        _validate_args(args)


def test_device_is_rejected_for_file_input():
    args = _parse("--input", "sample.wav", "--device", "2")
    with pytest.raises(ConfigurationError, match="only valid with --input mic"):
        _validate_args(args)
