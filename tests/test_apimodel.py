import typing

import pytest

import apimodel


class Inner(apimodel.APIModel):
    required: int
    optional: typing.Optional[str] = None


class Model(apimodel.APIModel):
    _special: object = apimodel.Extra()

    integer: int = 0
    string: str = ""

    nested: typing.Optional[Inner] = None


@pytest.fixture()
def model():
    model = Model({"string": "foo", "nested": {"required": "24"}}, special="SPECIAL_DATA")

    assert model._special == "SPECIAL_DATA"
    assert model.string == "foo"
    assert model.integer == 0
    assert model.nested
    assert model.nested.required == 24
    assert model.nested.optional is None

    return model


def test_as_dict(model: apimodel.APIModel):
    assert model.as_dict() == {"integer": 0, "string": "foo", "nested": {"required": 24, "optional": None}}


def test_get_extras(model: apimodel.APIModel):
    assert model.get_extras() == {"special": "SPECIAL_DATA"}


def test_validate():
    assert Model.validate_sync({"string": "foo"}) == {"integer": 0, "string": "foo", "nested": None}
