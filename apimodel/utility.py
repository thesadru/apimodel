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


class Representation:
    """Pydantic's Representation.

    Supports pretty repr and devtools.
    """

    def __repr_args__(self) -> typing.Mapping[str, typing.Any]:
        if __slots__ := getattr(self, "__slots__", ()):
            args = {k: getattr(self, k) for k in __slots__ if hasattr(self, k)}
        else:
            args = self.__dict__

        return {k: v for k, v in args.items() if k[0] != "_" and v != Ellipsis}

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.__repr_args__().items())
        return f"{self.__class__.__name__}({args})"

    def __pretty__(self, fmt: typing.Callable[[typing.Any], str], **kwargs: typing.Any) -> typing.Iterator[typing.Any]:
        """Devtools pretty formatting."""
        yield type(self).__name__
        yield "("
        yield 1

        for k, v in self.__repr_args__().items():
            yield k
            yield "="
            yield fmt(v)
            yield 0

        yield -1
        yield ")"

    def __copy__(self) -> typing_extensions.Self:
        return self.__class__(**self.__repr_args__())  # type: ignore


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


def as_universal(callback: typing.Callable[P, tutils.UniversalAsyncGenerator[T]]) -> UniversalAsync[P, T]:
    """Convert a callback to a UniversalAsync callback."""
    return UniversalAsync(callback)
