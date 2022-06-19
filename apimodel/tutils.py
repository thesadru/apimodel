"""Typing utils."""
from __future__ import annotations

import sys
import typing

if typing.TYPE_CHECKING:
    import typing_extensions

# Combinations of identical types
if sys.version_info >= (3, 10):
    from types import NoneType, UnionType

    UnionTypes: typing.Sequence[object] = (typing.Union, UnionType)
    NoneTypes: typing.Sequence[object] = (None, NoneType)

else:
    UnionTypes: typing.Sequence[object] = (typing.Union,)
    NoneTypes: typing.Sequence[object] = (None, type(None))


# Self
if sys.version_info >= (3, 11):
    Self = typing.Self
elif typing.TYPE_CHECKING:
    from typing_extensions import Self  # type: ignore # noqa
else:
    try:
        from typing_extensions import Self
    except ImportError:
        Self = typing.Any

# GenericAlias
if sys.version_info >= (3, 9):
    from types import GenericAlias
else:
    from typing import _GenericAlias as GenericAlias  # type: ignore # noqa

# Annotated and AnnotatedAlias
if sys.version_info >= (3, 9):
    Annotated = typing.Annotated
    AnnotatedAlias = type(typing.Annotated[object, object])
elif typing.TYPE_CHECKING:
    from typing_extensions import Annotated  # type: ignore # noqa
    from typing_extensions import _AnnotatedAlias as AnnotatedAlias  # type: ignore # noqa
else:
    try:
        from typing_extensions import Annotated  # type: ignore # noqa
        from typing_extensions import _AnnotatedAlias as AnnotatedAlias  # type: ignore # noqa

    except ImportError:

        class AnnotatedAlias(GenericAlias, _root=True):  # noqa
            def __init__(self, origin: type, metadata: object) -> None:
                super().__init__(origin, origin)
                self.__metadata__ = metadata

        Annotated: type = type("Annotated", (), {"__class_getitem__": lambda cls, *args: AnnotatedAlias(*args)})  # type: ignore


T = typing.TypeVar("T")
T1 = typing.TypeVar("T1")
T2 = typing.TypeVar("T2")

MaybeSequence = typing.Union[T, typing.Sequence[T]]
MaybeAwaitable = typing.Union[T, typing.Awaitable[T]]

JSONMapping = typing.Mapping[str, object]
AnyCallable = typing.Callable[..., typing.Any]
CallableT = typing.TypeVar("CallableT", bound=AnyCallable)
IdentityCallable = typing.Callable[[T], T]
DecoratorCallable = typing.Callable[[AnyCallable], T]
UniversalAsyncGenerator = typing.Generator[MaybeAwaitable[object], typing.Any, T]


RootValidatorSig = typing.Union[
    typing.Callable[[JSONMapping], MaybeAwaitable[JSONMapping]],
    typing.Callable[[typing.Any, JSONMapping], MaybeAwaitable[JSONMapping]],
]
ValidatorSig = typing.Union[
    typing.Callable[[typing.Any], MaybeAwaitable[object]],
    typing.Callable[[typing.Any, typing.Any], MaybeAwaitable[object]],
]


def lenient_issubclass(obj: object, tp: typing.Type[T]) -> typing_extensions.TypeGuard[typing.Type[T]]:
    """More lenient issubclass."""
    if isinstance(tp, GenericAlias):
        return obj == tp

    return isinstance(obj, type) and issubclass(obj, tp)
