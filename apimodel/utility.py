"""Utility functions for the library."""
from __future__ import annotations

import typing

from . import tutils

__all__ = ["Representation", "devtools_pretty"]

T = typing.TypeVar("T")
P = tutils.ParamSpec("P")


def flatten_sequences(*sequences: tutils.MaybeRecursiveSequence[T]) -> typing.Sequence[T]:
    """Flatten a possibly nested sequence."""
    joined: typing.Sequence[T] = []

    for sequence in sequences:
        if isinstance(sequence, typing.Sequence) and not isinstance(sequence, str):
            joined += flatten_sequences(*typing.cast("typing.Sequence[T]", sequence))
        else:
            joined.append(typing.cast("T", sequence))

    return joined


def devtools_pretty(
    fmt: typing.Callable[[object], str],
    *args: object,
    __name__: typing.Optional[str],
    **kwargs: object,
) -> typing.Iterator[object]:
    """Format args and kwargs for devtools."""
    if __name__:
        yield __name__
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

    if __name__:
        yield -1
        yield ")"


def make_pretty_signature(name: str, *args: object, **kwargs: object) -> typing.Callable[..., typing.Iterator[object]]:
    """Devtools pretty formatting for a higher order functions."""

    class Dummy:
        def __pretty__(self, fmt: typing.Callable[[object], str], **options: object) -> typing.Iterator[object]:
            yield from devtools_pretty(fmt, *args, __name__=name, **kwargs)

    return Dummy().__pretty__


def get_slots(cls: object) -> typing.Collection[str]:
    """Get all the slots for a class."""
    if not isinstance(cls, type):
        cls = cls.__class__

    slots: typing.Set[str] = set()
    for subclass in cls.mro():
        slots.update(getattr(subclass, "__slots__", ()))

    return slots


class Representation:
    """Pydantic's Representation.

    Supports pretty repr and devtools.
    """

    __slots__ = ()

    def __repr_args__(self) -> typing.Mapping[str, object]:
        args = {k: getattr(self, k) for k in get_slots(self) if hasattr(self, k)}
        if not args and hasattr(self, "__dict__"):
            args = self.__dict__

        return {k: v for k, v in args.items() if k[0] != "_" and v != Ellipsis}

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.__repr_args__().items())
        return f"{self.__class__.__name__}({args})"

    def __pretty__(self, fmt: typing.Callable[[object], str], **kwargs: object) -> typing.Iterator[object]:
        """Devtools pretty formatting."""
        yield from devtools_pretty(fmt, __name__=self.__class__.__name__, **self.__repr_args__())


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


def as_universal(callback: typing.Callable[P, tutils.UniversalAsyncGenerator[T]]) -> UniversalAsync[P, T]:
    """Convert a callback to a UniversalAsync callback."""
    return UniversalAsync(callback)
