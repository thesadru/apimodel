import typing
from unittest import mock

import pytest

import apimodel


class Inner(apimodel.APIModel):
    required: int
    optional: typing.Optional[str] = None

    @property
    def magic(self) -> int:
        return 42

    @apimodel.named_property(exclude=True)
    def special_magic(self):
        return "NOT INCLUDED"


class Model(apimodel.APIModel):
    _special: object = apimodel.Extra()

    integer: int = 0
    string: str = ""
    array: typing.List[str] = apimodel.Field(default_factory=list)

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


def test_as_dict(model: apimodel.APIModel) -> None:
    assert model.as_dict() == {
        "integer": 0,
        "string": "foo",
        "array": [],
        "nested": {"required": 24, "optional": None, "magic": 42},
    }


def test_get_extras(model: apimodel.APIModel) -> None:
    assert model.get_extras() == {"special": "SPECIAL_DATA"}


def test_validate():
    assert Model.validate.synchronous({"string": "foo", "array": (1, 2)}) == {
        "integer": 0,
        "string": "foo",
        "array": ["1", "2"],
        "nested": None,
    }


def test_pretty():
    fmt = mock.Mock()
    gen: typing.Iterator[object] = Model.__pretty__(fmt)  # type: ignore

    assert list(gen)
    assert fmt.call_count == 7  # extra, 3 attrs, 1 nest, 2 nested attrs
