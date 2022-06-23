"""Test async callbacks."""
import typing

import pytest

import apimodel


class Inner(apimodel.APIModel):
    baz: float = 0.02

    @apimodel.validator("baz")
    async def validate_foo(self, value: int) -> int:
        return round(value, 2)


class AsyncModel(apimodel.APIModel):
    foo: int
    bar: str

    inner: typing.Optional[Inner] = None

    @apimodel.validator("foo")
    def validate_foo(self, value: int) -> int:
        if value < 10:
            value += 10

        return value

    @apimodel.validator("bar")
    async def validate_bar(self, value: str) -> str:
        return value + "!"

    @apimodel.root_validator(order=apimodel.Order.INITIAL_ROOT)
    async def validate_root(self, values: typing.Mapping[str, object]) -> typing.Mapping[str, object]:
        assert len(values) == 3
        return values


def test_sync_create() -> None:
    with pytest.raises(TypeError, match="Must use the create method with an async APIModel."):
        AsyncModel(foo=1, bar="bar")


async def test_async_validators() -> None:
    assert AsyncModel.isasync

    model = await AsyncModel.create(foo=1, bar="bar", inner={"baz": 0.013})

    assert model.foo == 11
    assert model.bar == "bar!"
    assert model.inner and model.inner.baz == 0.01
