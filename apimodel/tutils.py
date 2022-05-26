"""Typing utils."""
from __future__ import annotations

import sys
import typing

if typing.TYPE_CHECKING:
    import typing_extensions

if sys.version_info >= (3, 10):
    from types import NoneType, UnionType

    UnionTypes: typing.Set[typing.Any] = {typing.Union, UnionType}
    NoneTypes: typing.Set[typing.Any] = {None, NoneType}

else:
    UnionTypes: typing.Set[typing.Any] = {typing.Union}
    NoneTypes: typing.Set[typing.Any] = {None, type(None)}

AnnotatedAlias = type(typing.Annotated[object, object])

T = typing.TypeVar("T")
T1 = typing.TypeVar("T1")
T2 = typing.TypeVar("T2")


JSONMapping = typing.Mapping[str, typing.Any]
AnyCallable = typing.Callable[..., typing.Any]
AnyCallableT = typing.TypeVar("AnyCallableT", bound=AnyCallable)
IdentityCallable = typing.Callable[[T], T]
DecoratorCallable = typing.Callable[[AnyCallable], T]

MaybeSequence = typing.Union[T, typing.Sequence[T]]
MaybeAwaitable = typing.Union[T, typing.Awaitable[T]]

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
    if isinstance(tp, typing._GenericAlias):  # type: ignore
        return obj == tp

    return isinstance(obj, type) and issubclass(obj, tp)
