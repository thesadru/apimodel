"""Typing utils."""
from __future__ import annotations

import sys
import typing

if typing.TYPE_CHECKING:
    import typing_extensions

if sys.version_info >= (3, 10):
    from types import NoneType, UnionType

    UnionTypes: typing.Set[object] = {typing.Union, UnionType}
    NoneTypes: typing.Set[object] = {None, NoneType}

else:
    UnionTypes: typing.Set[object] = {typing.Union}
    NoneTypes: typing.Set[object] = {None, type(None)}

if sys.version_info >= (3, 9):
    Annotated = typing.Annotated
    AnnotatedAlias = type(typing.Annotated[object, object])
else:
    AnnotatedAlias: typing.Type[object] = type("AnnotatedAlias", (), {})
    Annotated: object = AnnotatedAlias()

if sys.version_info >= (3, 9):
    from types import GenericAlias
else:
    from typing import _GenericAlias as GenericAlias  # type: ignore

T = typing.TypeVar("T")
T1 = typing.TypeVar("T1")
T2 = typing.TypeVar("T2")

MaybeSequence = typing.Union[T, typing.Sequence[T]]
MaybeAwaitable = typing.Union[T, typing.Awaitable[T]]

JSONMapping = typing.Mapping[str, typing.Any]
AnyCallable = typing.Callable[..., typing.Any]
AnyCallableT = typing.TypeVar("AnyCallableT", bound=AnyCallable)
IdentityCallable = typing.Callable[[T], T]
DecoratorCallable = typing.Callable[[AnyCallable], T]
UniversalAsyncGenerator = typing.Generator[MaybeAwaitable[T], T, T]


RootValidatorSig = typing.Union[
    typing.Callable[[JSONMapping], MaybeAwaitable[JSONMapping]],
    typing.Callable[[typing.Any, JSONMapping], MaybeAwaitable[JSONMapping]],
]
ValidatorSig = typing.Union[
    typing.Callable[[typing.Any], MaybeAwaitable[typing.Any]],
    typing.Callable[[typing.Any, typing.Any], MaybeAwaitable[typing.Any]],
]


def lenient_issubclass(obj: typing.Any, tp: typing.Type[T]) -> typing_extensions.TypeGuard[typing.Type[T]]:
    """More lenient issubclass."""
    if isinstance(tp, GenericAlias):
        return obj == tp

    return isinstance(obj, type) and issubclass(obj, tp)
