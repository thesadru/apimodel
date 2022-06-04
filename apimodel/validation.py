"""Validators used in fields and models."""
from __future__ import annotations

import asyncio
import enum
import typing

from . import tutils, utility

__all__ = ["Order", "RootValidator", "Validator", "root_validator", "validator"]


T = typing.TypeVar("T")


class Order(enum.IntEnum):
    """The order of a validator."""

    def _generate_next_value_(self, start: int, count: int, last_values: typing.Sequence[object]) -> int:
        return (count) * 10

    INITIAL_ROOT = enum.auto()
    # ALIAS
    ROOT = enum.auto()
    VALIDATOR = enum.auto()
    ANNOTATION = enum.auto()
    POST_VALIDATOR = enum.auto()
    FINAL_ROOT = enum.auto()


class BaseValidator(utility.Representation):
    """Base class for validators."""

    __slots__ = ("callback", "order", "bound")

    callback: tutils.AnyCallable

    order: int
    bound: bool

    def __init__(self, callback: tutils.AnyCallable, *, order: int):
        self.callback = callback
        self.order = order

        self.bound = False

    def __call__(self, model: object, value: object) -> tutils.MaybeAwaitable[typing.Any]:
        """Call the validator and optionally give it a model.

        May return an Awaitable if the callback is async.
        """
        if self.bound:
            return self.callback(model, value)
        else:
            return self.callback(value)

    @property
    def isasync(self) -> bool:
        """Whether the callback returns an awaitable."""
        return asyncio.iscoroutinefunction(self.callback)

    @property
    def _is_coroutine(self) -> object:
        """Helper attribute for asyncio.iscoroutinefunction."""
        if self.isasync:
            return getattr(asyncio.coroutines, "_is_coroutine")
        else:
            return None


class Validator(BaseValidator):
    """Basic validator for a single value."""

    _fields: typing.Sequence[str] = ()

    def __init__(self, callback: tutils.AnyCallable, *, order: int = Order.VALIDATOR) -> None:
        super().__init__(callback, order=order)

    def __call__(self, model: object, value: object) -> tutils.MaybeAwaitable[object]:
        """Call the validator with a single value and optionally give it a model.

        May return an Awaitable if the callback is async.
        """
        return super().__call__(model, value)


class RootValidator(BaseValidator):
    """Root validator for an entire model."""

    def __init__(self, callback: tutils.AnyCallable, *, order: int = Order.INITIAL_ROOT):
        super().__init__(callback, order=order)

    def __call__(self, model: object, values: tutils.JSONMapping) -> tutils.MaybeAwaitable[tutils.JSONMapping]:
        """Call the validator with its dict and optionally give it a model.

        May return an Awaitable if the callback is async.
        """
        return super().__call__(model, values)


def validator(*fields: str, order: int = Order.VALIDATOR) -> tutils.DecoratorCallable[Validator]:
    """Create a validator for one or more fields."""

    def decorator(callback: tutils.AnyCallable) -> Validator:
        validator = Validator(callback, order=order)
        validator._fields = fields
        validator.bound = True
        return validator

    return decorator


def root_validator(order: int = Order.ROOT) -> tutils.DecoratorCallable[RootValidator]:
    """Create a root validator."""

    def decorator(callback: tutils.AnyCallable) -> RootValidator:
        validator = RootValidator(callback, order=order)
        validator.bound = True
        return validator

    return decorator
