"""Utility functions for the library."""
from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    import typing_extensions

    P = typing_extensions.ParamSpec("P")
else:
    P = typing.TypeVar("P")

from . import tutils

__all__ = ["Representation"]

T = typing.TypeVar("T")


def get_slots(cls: object) -> typing.Collection[str]:
    """Get all the slots for a class."""
    slots: typing.Set[str] = set()
    for subclass in cls.__class__.mro():
        slots.update(getattr(subclass, "__slots__", ()))

    return slots


class Representation:
    """Pydantic's Representation.

    Supports pretty repr and devtools.
    """

    __slots__ = ()

    def __repr_args__(self) -> typing.Mapping[str, object]:
        if hasattr(self, "__slots__"):
            args = {k: getattr(self, k) for k in get_slots(self) if hasattr(self, k)}
        else:
            args = self.__dict__

        return {k: v for k, v in args.items() if k[0] != "_" and v != Ellipsis}

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.__repr_args__().items())
        return f"{self.__class__.__name__}({args})"

    def __pretty__(self, fmt: typing.Callable[[object], str], **kwargs: object) -> typing.Iterator[object]:
        """Devtools pretty formatting."""
        yield type(self).__name__
        yield "("
        yield 1

        for k, v in self.__repr_args__().items():
            yield k
            yield "="
            yield fmt(v)
            yield ","
            yield 0

        yield -1
        yield ")"


class UniversalAsync(typing.Generic[P, T]):
    """Compatibility for both sync and async callbacks."""

    __slots__ = ("callback",)
    callback: typing.Callable[P, tutils.UniversalAsyncGenerator[T]]

    def __init__(self, callback: typing.Callable[P, tutils.UniversalAsyncGenerator[T]]) -> None:
        self.callback = callback

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> tutils.UniversalAsyncGenerator[T]:
        return self.callback(*args, **kwargs)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.callback!r})"

    @property
    def __name__(self) -> str:
        return self.callback.__name__

    def synchronous(self, *args: P.args, **kwargs: P.kwargs) -> T:
        """Run the callback synchronously."""
        generator = self.callback(*args, **kwargs)

        try:
            value = generator.__next__()

            while True:
                if isinstance(value, typing.Awaitable):
                    raise TypeError("Received awaitable in sync mode.")

                value = generator.send(value)
        except StopIteration as e:
            return e.value

    async def asynchronous(self, *args: P.args, **kwargs: P.kwargs) -> T:
        """Run the callback asynchronously."""
        generator = self.callback(*args, **kwargs)

        try:
            value = generator.__next__()

            while True:
                if isinstance(value, typing.Awaitable):
                    value = typing.cast("T", await value)

                value = generator.send(value)
        except StopIteration as e:
            return e.value

    def __pretty__(self, fmt: typing.Callable[[object], str], **kwargs: object) -> typing.Iterator[object]:
        """Devtools pretty formatting."""
        yield fmt(self.callback)


def make_pretty_signature(name: str, *args: object, **kwargs: object) -> typing.Callable[..., typing.Iterator[object]]:
    """Devtools pretty formatting for a higher order functions."""

    class Dummy:
        def __pretty__(self, fmt: typing.Callable[[object], str], **options: object) -> typing.Iterator[object]:
            yield name
            yield "("
            yield 1

            for v in args:
                yield fmt(v)
                yield ","
                yield 0

            for k, v in kwargs.items():
                yield k
                yield "="
                yield fmt(v)
                yield ","
                yield 0

            yield -1
            yield ")"

    return Dummy().__pretty__


def as_universal(callback: typing.Callable[P, tutils.UniversalAsyncGenerator[T]]) -> UniversalAsync[P, T]:
    """Convert a callback to a UniversalAsync callback."""
    return UniversalAsync(callback)
