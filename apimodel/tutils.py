"""Backwards-compatible types and typing utilities."""
from __future__ import annotations

import sys
import typing

__all__ = ["generic_isinstance", "lenient_issubclass"]

# ==============================================================================
# Backwards compatibility imports
# ==============================================================================

# GenericAlias
if typing.TYPE_CHECKING:
    from types import GenericAlias
else:
    from typing import _GenericAlias as GenericAlias  # type: ignore # noqa


def _make_generic_alias_factory(name: str, getitem_cls: typing.Callable[..., object]) -> typing.Type[typing.Any]:
    """Make a generic alias with an output class."""
    return type(name, (), {"__class_getitem__": lambda cls, *args: getitem_cls(*args)})  # type: ignore


# Self
if sys.version_info >= (3, 11):
    Self = typing.Self
elif typing.TYPE_CHECKING:
    from typing_extensions import Self  # type: ignore # noqa
else:
    try:
        from typing_extensions import Self
    except ImportError:
        Self = typing.TypeVar("Self")

# Combinations of identical types
if sys.version_info >= (3, 10):
    from types import NoneType, UnionType

    UnionTypes: typing.Sequence[object] = (typing.Union, UnionType)
    NoneTypes: typing.Sequence[object] = (None, NoneType)

else:
    UnionTypes: typing.Sequence[object] = (typing.Union,)
    NoneTypes: typing.Sequence[object] = (None, type(None))

# TypeGuard
if sys.version_info >= (3, 10):
    TypeGuard = typing.TypeGuard
elif typing.TYPE_CHECKING:
    from typing_extensions import TypeGuard  # type: ignore # noqa
else:
    try:
        from typing_extensions import TypeGuard  # type: ignore # noqa
    except ImportError:
        TypeGuard: typing.Type[typing.Any] = _make_generic_alias_factory("TypeGuard", lambda *args: bool)  # type: ignore

# ParamSpec
if sys.version_info >= (3, 10):
    ParamSpec = typing.ParamSpec
    Concatenate = typing.Concatenate
elif typing.TYPE_CHECKING:
    from typing_extensions import Concatenate, ParamSpec  # type: ignore # noqa
else:
    try:
        from typing_extensions import Concatenate, ParamSpec  # type: ignore # noqa
    except ImportError:
        ParamSpec = typing.TypeVar
        Concatenate: type = _make_generic_alias_factory("Concatenate", list)


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

        Annotated: type = _make_generic_alias_factory("Annotated", AnnotatedAlias)


# ==============================================================================
# type definitions
# ==============================================================================

T = typing.TypeVar("T")
T1 = typing.TypeVar("T1")
T2 = typing.TypeVar("T2")

MaybeSequence = typing.Union[T, typing.Sequence[T]]
MaybeRecursiveSequence = typing.Union[T, typing.Sequence["MaybeRecursiveSequence[T]"]]
MaybeTuple = typing.Union[T, typing.Tuple[T, ...]]
MaybeAwaitable = typing.Union[T, typing.Awaitable[T]]
MaybeType = typing.Union[T, typing.Type[T]]

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


def lenient_issubclass(obj: object, tp: typing.Type[T]) -> TypeGuard[typing.Type[T]]:
    """More lenient issubclass."""
    if isinstance(tp, GenericAlias):
        if obj == tp:
            return True

        tp = tp.__origin__  # type: ignore  # apparently Never

    return isinstance(obj, type) and issubclass(obj, tp)


def generic_isinstance(
    obj: object,
    tp: MaybeSequence[typing.Type[T]],
    *,
    exclude: MaybeSequence[typing.Type[object]] = (),
) -> TypeGuard[T]:
    """Whether an object is an instance of a generic type."""
    from . import utility

    include = [typing.get_origin(t) or t for t in utility.flatten_sequences(tp)]
    exclude = [typing.get_origin(t) or t for t in utility.flatten_sequences(exclude)]

    return any(isinstance(obj, t) for t in include) and not any(isinstance(obj, t) for t in exclude)
