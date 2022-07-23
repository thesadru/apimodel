"""Test generic models."""
import typing

import apimodel

T = typing.TypeVar("T")
T1 = typing.TypeVar("T1")
T2 = typing.TypeVar("T2")


class GenericModel(apimodel.APIModel, typing.Generic[T1, T2]):
    x: T1
    y: T2


class PartiallyResolved(GenericModel[int, T]):
    ...


class Resolved(PartiallyResolved[str]):
    ...


class NestedGeneric(apimodel.APIModel):
    gen: PartiallyResolved[str]


def test_generic_models() -> None:
    model = GenericModel[object, object](x="1", y=2)
    assert model.x == "1"
    assert model.y == 2

    model = Resolved(x="1", y=2)
    assert model.x == 1
    assert model.y == "2"


def test_nested_generic_models() -> None:
    model = NestedGeneric(gen=dict(x="1", y=2))

    assert model.gen.x == 1
    assert model.gen.y == "2"
