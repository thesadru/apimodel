"""Test async callbacks."""
import typing

import pytest

import apimodel


class AsyncModel(apimodel.APIModel):
    foo: int
    bar: str

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
        assert len(values) == 2
        return values


def test_sync_create() -> None:
    with pytest.raises(TypeError, match="Must use the create method with an async APIModel."):
        AsyncModel(foo=1, bar="bar")


async def test_async_validators() -> None:
    assert AsyncModel.isasync

    model = await AsyncModel.create(foo=1, bar="bar")

    assert model.foo == 11
    assert model.bar == "bar!"
