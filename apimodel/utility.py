"""Utility functions for the library."""
from __future__ import annotations

import asyncio
import contextlib
import inspect
import typing

from . import tutils

__all__ = ["Representation"]

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

    # dict required for ordering
    slots: typing.Dict[str, None] = {}
    for subclass in reversed(cls.mro()):
        slots.update(dict.fromkeys(getattr(subclass, "__slots__", ())))

    return tuple(slots)


def resolve_typevars(cls: type) -> typing.Mapping[str, object]:
    """Resolve typevar names to types."""
    typevars: typing.Mapping[str, object] = {}

    orig_bases: typing.Sequence[typing.Any] = getattr(cls, "__orig_bases__", ())

    for base in orig_bases:
        if not isinstance(base, tutils.GenericAlias):
            continue

        parameters: typing.Sequence[typing.TypeVar] = getattr(base.__origin__, "__parameters__", ())
        if not parameters:
            continue

        args: typing.Sequence[object] = base.__args__

        # requiring typevars to be repeated makes resolving much easier
        if len(args) != len(parameters):
            raise TypeError(f"Typevars in {base} must be repeated: {args} X {parameters}")

        for tp, typevar in zip(args, parameters):
            if typevar.__name__ in typevars:
                raise TypeError(f"Duplicate typevar: {typevar}")

            typevars[typevar.__name__] = tp

        # unresolved typevars may have been renamed
        subclass_typevars = resolve_typevars(base.__origin__)
        for key, tp in subclass_typevars.items():
            if isinstance(tp, typing.TypeVar):
                tp = typevars.get(tp.__name__, tp)

            typevars[key] = tp

    # add unresolved typevars
    parameters = getattr(cls, "__parameters__", ())
    for typevar in parameters:
        typevars.setdefault(typevar.__name__, typevar)

    return typevars


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

    callback: typing.Callable[P, tutils.MaybeAwaitable[T]]

    def __init__(self, callback: typing.Callable[P, tutils.MaybeAwaitable[T]]) -> None:
        if isinstance(callback, UniversalAsync):
            callback = callback.callback

        self.callback = callback

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        return await self.asynchronous(*args, **kwargs)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.callback!r})"

    @property
    def __name__(self) -> str:
        return self.callback.__name__

    @property
    def __signature__(self) -> inspect.Signature:
        return inspect.signature(self.callback)

    def synchronous(self, *args: P.args, **kwargs: P.kwargs) -> T:
        """Run the callback synchronously."""
        r = self.callback(*args, **kwargs)
        if not inspect.isawaitable(r):
            return typing.cast("T", r)

        with contextlib.closing(r.__await__()) as gen:
            try:
                future = gen.send(None)
            except StopIteration as e:
                return e.value
            else:
                raise RuntimeError(f"Coroutine {self.callback!r} is not synchronous.\nReceived {future!r}")

    async def asynchronous(self, *args: P.args, **kwargs: P.kwargs) -> T:
        """Run the callback asynchronously."""
        r = self.callback(*args, **kwargs)
        if not inspect.isawaitable(r):
            return typing.cast("T", r)

        return await r

    if not typing.TYPE_CHECKING:

        def __getattribute__(self, name: str) -> typing.Any:
            """Optimize directly getting asynchronous."""
            if name in ("synchronous", "asynchronous"):
                isasync = asyncio.iscoroutinefunction(self.callback)
                if name == "synchronous" and not isasync and "async" not in self.callback.__name__:
                    return self.callback
                if name == "asynchronous" and isasync:
                    return self.callback

            return super().__getattribute__(name)

    def __pretty__(self, fmt: typing.Callable[[object], str], **kwargs: object) -> typing.Iterator[object]:
        """Devtools pretty formatting."""
        yield fmt(self.callback)

    @typing.overload
    def __get__(
        self: UniversalAsync[P, T],
        instance: typing.Optional[object],
        owner: typing.Optional[typing.Type[object]],
    ) -> UniversalAsync[P, T]:
        ...

    @typing.overload
    def __get__(
        self: UniversalAsync[tutils.Concatenate[typing.Any, P], T],
        instance: object,
        owner: typing.Optional[typing.Type[object]],
    ) -> UniversalAsync[P, T]:
        ...

    def __get__(
        self,
        instance: typing.Optional[object],
        owner: typing.Optional[typing.Type[object]],
    ) -> UniversalAsync[..., T]:
        callback = self.callback.__get__(instance, owner)
        return self.__class__(callback)


def as_universal(callback: typing.Callable[P, tutils.MaybeAwaitable[T]]) -> UniversalAsync[P, T]:
    """Convert a callback to a UniversalAsync callback."""
    return UniversalAsync(callback)


def as_universal_method(
    callback: typing.Callable[tutils.Concatenate[typing.Any, P], tutils.MaybeAwaitable[T]]
) -> UniversalAsync[P, T]:
    """Convert a callback to a UniversalAsync callback.

    Simulates a method in its typing to help type-checkers.
    """
    return typing.cast("UniversalAsync[P, T]", UniversalAsync(callback))
