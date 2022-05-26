"""Utility functions for the library."""
from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    import typing_extensions

__all__ = ["Representation"]


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
