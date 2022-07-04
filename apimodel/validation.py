"""Validators used in fields and models."""
from __future__ import annotations

import asyncio
import enum
import inspect
import typing

from . import tutils, utility

__all__ = ["Order", "RootValidator", "Validator", "root_validator", "validator"]


T = typing.TypeVar("T")


class Order(enum.IntEnum):
    """The order of a validator."""

    def _generate_next_value_(self, start: int, count: int, last_values: typing.Sequence[object]) -> int:
        return count * 10

    INITIAL_ROOT = enum.auto()
    """Root Validator acting upon the completely raw data."""

    ROOT = enum.auto()
    """Root Validator acting upon the data with converted names."""

    VALIDATOR = enum.auto()
    """Validator acting upon a field before annotation conversion."""

    ANNOTATION = enum.auto()
    """Annotation Validator. Not meant to be defined by the user."""

    POST_VALIDATOR = enum.auto()
    """Validator acting upon a field after annotation conversion."""

    FINAL_ROOT = enum.auto()
    """Root Validator acting upon the data after individual field conversion."""


class BaseValidator(utility.Representation):
    """Base class for validators."""

    __slots__ = ("callback", "order", "bound")

    callback: tutils.AnyCallable

    order: int
    bound: bool

    def __init__(self, callback: tutils.AnyCallable, *, order: int) -> None:
        """Initialize a validator.

        Validators are unbound by default.
        """
        self.callback = callback
        self.order = order

        self.bound = False

    async def __call__(self, model: object, value: object) -> typing.Any:
        """Call the validator and optionally give it a model."""
        return await self.asynchronous(model, value)

    @utility.as_universal_method
    def asynchronous(self, model: object, value: object) -> typing.Any:
        """Call the validator and optionally give it a model."""
        if self.bound:
            return self.callback(model, value)
        else:
            return self.callback(value)

    def synchronous(self, model: object, value: object) -> typing.Any:
        """Call the validator and optionally give it a model."""
        return self.asynchronous.synchronous(model, value)

    @property
    def isasync(self) -> bool:
        """Whether the callback returns an awaitable."""
        return inspect.iscoroutinefunction(self.callback)

    @property
    def _is_coroutine(self) -> object:
        """Helper attribute for asyncio.iscoroutinefunction."""
        if self.isasync:
            return getattr(asyncio.coroutines, "_is_coroutine")
        else:
            return None


class Validator(BaseValidator):
    """Basic validator for a single value."""

    __slots__ = ("_fields",)

    _fields: typing.Sequence[str]

    def __init__(self, callback: tutils.AnyCallable, *, order: int = Order.VALIDATOR) -> None:
        """Initialize a standard field validator. Order cannot have ROOT."""
        self._fields = ()
        super().__init__(callback, order=order)


class RootValidator(BaseValidator):
    """Root validator for an entire model."""

    __slots__ = ()

    def __init__(self, callback: tutils.AnyCallable, *, order: int = Order.INITIAL_ROOT) -> None:
        """Initialize a root validator. Order must have ROOT."""
        super().__init__(callback, order=order)

    async def __call__(self, model: object, values: tutils.JSONMapping) -> tutils.JSONMapping:
        """Call the validator with its dict and optionally give it a model.

        May return an Awaitable if the callback is async.
        """
        return await super().__call__(model, values)


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
