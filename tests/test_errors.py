import typing
from unittest import mock

import pytest

import apimodel


@pytest.fixture()
def error_list() -> typing.Sequence[apimodel.errors.ErrorList]:
    model: typing.Any = mock.Mock()
    model.__name__ = "Root"

    return [
        apimodel.errors.LocError(
            apimodel.errors.ValidationError(
                apimodel.errors.LocError(ValueError("error"), "attribute"),
                model=model,
            ),
            "nested",
        ),
        apimodel.errors.LocError(
            apimodel.errors.ValidationError(
                apimodel.errors.LocError(TypeError("error"), 1),
                model=model,
            ),
            "array",
        ),
    ]


def test_validation_error_loc(error_list: typing.Sequence[apimodel.errors.ErrorList]) -> None:
    errors = list(apimodel.errors.flatten_errors(error_list))

    assert errors[0][0] == ("nested", "attribute")
    assert errors[1][0] == ("array", 1)
