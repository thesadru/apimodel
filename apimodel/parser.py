"""Parser functions for various types."""
from __future__ import annotations

import asyncio
import datetime
import enum
import functools
import inspect
import sys
import typing
import warnings
from unittest.mock import _Call as Call

from . import apimodel, errors, tutils, utility, validation

__all__ = ["cast", "get_validator", "validate_arguments"]

T = typing.TypeVar("T")


class AnnotationValidator(validation.Validator):
    """Special validator for annotations."""

    __slots__ = ("tp",)

    tp: object

    def __init__(self, callback: tutils.AnyCallable) -> None:
        """Initialize an AnnotationValidator.

        The callback must have an annotated return type.
        """
        super().__init__(callback, order=validation.Order.ANNOTATION)

        try:
            self.tp = typing.get_type_hints(callback)["return"]
        except Exception:
            self.tp = object

    def __repr_args__(self) -> typing.Mapping[str, object]:
        return {"callback": self.callback}


def as_validator(callback: tutils.ValidatorSig) -> AnnotationValidator:
    """Convert a validator function to a validator class."""
    signature = inspect.signature(callback)
    validator = AnnotationValidator(callback)
    if len(signature.parameters) >= 2:
        validator.bound = True

    return validator


def debuggable_deco(func: tutils.CallableT) -> tutils.CallableT:
    """Make a higher order function's return debuggable."""

    def wrapper(*args: object, **kwargs: object) -> object:
        obj = func(*args, **kwargs)
        if not callable(obj):
            return obj

        callback = obj
        if isinstance(obj, validation.Validator):
            callback = obj.callback
        if inspect.ismethod(callback) and isinstance(callback.__self__, utility.UniversalAsync):
            callback = callback.__self__.callback

        call = Call((func.__name__, args, kwargs))
        notation = repr(call)[5:]
        if asyncio.iscoroutinefunction(obj):
            notation = "async " + notation

        if inspect.isfunction(callback):
            callback.__qualname__ = notation

        if not hasattr(callback, "__pretty__"):
            callback.__pretty__ = utility.make_pretty_signature(func.__name__, *args, **kwargs)  # type: ignore

        return obj

    return typing.cast("tutils.CallableT", wrapper)


@as_validator
def datetime_validator(value: typing.Union[datetime.datetime, str, int, float]) -> datetime.datetime:
    """Parse a datetime."""
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)

        return value.astimezone(datetime.timezone.utc)

    try:
        value = float(value)
    except ValueError:
        pass

    if isinstance(value, (int, float)):
        # attempt to parse unix
        return datetime.datetime.fromtimestamp(value, tz=datetime.timezone.utc)

    # unsupported by the builtin parser
    value = value.rstrip("Z")
    value = datetime.datetime.fromisoformat(value)
    return datetime_validator.callback(value)


@as_validator
def timedelta_validator(value: typing.Union[str, int, float]) -> datetime.timedelta:
    """Parse a timedelta."""
    # TODO: Support ISO8601
    if isinstance(value, datetime.timedelta):
        return value

    value = float(value)
    return datetime.timedelta(seconds=value)


@as_validator
def noop_validator(value: object) -> object:
    """Return the value."""
    return value


@debuggable_deco
def cast_validator(callback: typing.Callable[[typing.Any], object]) -> AnnotationValidator:
    """Cast the value to the given type."""

    @as_validator
    def validator(value: object) -> object:
        return callback(value)

    return validator


@debuggable_deco
def arbitrary_validator(tp: type) -> AnnotationValidator:
    """Expect a specific type of value."""

    @as_validator
    def validator(value: object) -> object:
        if isinstance(value, tp):
            return value

        raise TypeError(f"Expected {tp}, got {value}")

    return validator


@debuggable_deco
def literal_validator(values: typing.Collection[object]) -> AnnotationValidator:
    """Check if the value is one of the given literals."""
    values = set(values)

    @as_validator
    def validator(value: object) -> object:
        if value in values:
            return value

        if len(values) == 1:
            (expected,) = values
            raise TypeError(f"Expected {expected}, got {value!r}")
        else:
            raise TypeError(f"Expected one of {values}, got {value!r}")

    return validator


@debuggable_deco
def enum_validator(enum_type: typing.Type[enum.Enum]) -> AnnotationValidator:
    """Validate an enum."""
    if sys.version_info >= (3, 11):
        warnings.warn("Enums are unstable in python >=3.11.")
        if issubclass(enum_type, enum.IntEnum):
            tp = int
        elif issubclass(enum_type, enum.StrEnum):
            tp = str
        else:
            tp = object
    elif len(enum_type.__mro__) >= 3 and not tutils.lenient_issubclass(enum_type.__mro__[-3], enum.Enum):
        tp = enum_type.__mro__[-3]
    else:
        tp = object

    try:
        inner_validator = get_validator(tp)
    except Exception:
        inner_validator = noop_validator

    @utility.as_universal
    async def validator(model: apimodel.APIModel, value: object) -> object:
        value = await inner_validator(model, value)
        return typing.cast("enum.Enum", enum_type(value))

    if inner_validator.isasync:
        return as_validator(validator.asynchronous)
    else:
        return as_validator(validator.synchronous)


@debuggable_deco
def collection_validator(
    collection_type: typing.Callable[[typing.Collection[typing.Any]], typing.Collection[object]],
    inner_validator: validation.Validator,
) -> AnnotationValidator:
    """Validate the items of a collection."""
    collection_type = typing.get_origin(collection_type) or collection_type

    if inspect.isabstract(collection_type):
        if tutils.lenient_issubclass(collection_type, typing.MutableSequence):
            collection_type = list
        elif tutils.lenient_issubclass(collection_type, typing.MutableSet):
            collection_type = set
        elif tutils.lenient_issubclass(collection_type, typing.Set):
            collection_type = frozenset
        else:
            collection_type = tuple

    @utility.as_universal
    async def validator(model: apimodel.APIModel, value: object) -> typing.Collection[object]:
        if not isinstance(value, typing.Iterable):
            raise TypeError(f"Expected iterable, got {type(value)}")

        value = typing.cast("typing.Iterable[object]", value)

        items: typing.Collection[object] = []

        with errors.catch_errors(model) as catcher:
            for index, item in enumerate(value):
                with catcher.catch(loc=index):
                    items.append((await inner_validator(model, item)))

        return collection_type(items)

    if inner_validator.isasync:
        return as_validator(validator.asynchronous)
    else:
        return as_validator(validator.synchronous)


@debuggable_deco
def mapping_validator(
    mapping_type: typing.Callable[[typing.Mapping[typing.Any, typing.Any]], typing.Mapping[object, object]],
    key_validator: validation.Validator,
    value_validator: validation.Validator,
) -> AnnotationValidator:
    """Validate the keys and values of a mapping."""
    mapping_type = typing.get_origin(mapping_type) or mapping_type

    if inspect.isabstract(mapping_type):
        mapping_type = dict

    @utility.as_universal
    async def validator(model: apimodel.APIModel, value: object) -> object:
        if not isinstance(value, typing.Mapping):
            raise TypeError(f"Expected mapping, got {type(value)}")

        value = typing.cast("typing.Mapping[object, object]", value)

        mapping: typing.Mapping[object, object] = {}

        with errors.catch_errors(model) as catcher:
            for key in value:
                with catcher.catch(loc=str(key)):
                    mapping[(await key_validator(model, key))] = await value_validator(model, value[key])

        return mapping_type(mapping)

    if key_validator.isasync or value_validator.isasync:
        return as_validator(validator.asynchronous)
    else:
        return as_validator(validator.synchronous)


@debuggable_deco
def union_validator(validators: typing.Sequence[validation.Validator]) -> AnnotationValidator:
    """Return the first successful validator."""
    # shift None to the start
    new_validators = [
        validator
        for validator in validators
        if isinstance(validator, AnnotationValidator) and validator.tp not in tutils.NoneTypes
    ]
    if len(validators) != len(new_validators):
        validators = [RAW_VALIDATORS[None]] + new_validators

    @utility.as_universal
    async def validator(model: apimodel.APIModel, value: object) -> object:
        catcher = errors.ErrorCatcher(model)
        for index, validator in enumerate(validators):
            with catcher.catch(loc=f"Union[{index}]"):
                return await validator(model, value)

        catcher.raise_errors()

    if any(validator.isasync for validator in validators):
        return as_validator(validator.asynchronous)
    else:
        return as_validator(validator.synchronous)


@debuggable_deco
def model_validator(model: typing.Type[apimodel.APIModel]) -> AnnotationValidator:
    """Validate a model."""
    # TODO: Generics

    @as_validator
    def sync_validator(root: apimodel.APIModel, value: object) -> object:
        if isinstance(value, model):
            return value

        return model(value, **root.get_extras())

    @as_validator
    async def async_validator(root: apimodel.APIModel, value: object) -> object:
        if isinstance(value, model):
            return value

        return await model.create(value, **root.get_extras())

    if model.isasync:
        return async_validator
    else:
        return sync_validator


@debuggable_deco
def tuple_validator(tup: typing.Type[typing.Tuple[object, ...]]) -> AnnotationValidator:
    """Validate a namedtuple."""
    if hasattr(tup, "_fields"):
        name = tup.__name__
        types = getattr(tup, "_field_types", {}) or getattr(tup, "__annotations__", {})
        fields = getattr(tup, "_fields", tuple(types.keys()))
        defaults = getattr(tup, "_field_defaults", {})
    else:
        name = "Tuple"
        types = {f"field_{i}": x for i, x in enumerate(typing.get_args(tup))}
        fields = tuple(types.keys())
        defaults = {}

    definitions = {name: (types.get(name, object), defaults.get(name, ...)) for name in fields}
    model = apimodel.create_model(name, **definitions)

    @utility.as_universal
    async def validator(root: apimodel.APIModel, value: object) -> typing.Tuple[object, ...]:
        items: typing.Mapping[str, object]

        if isinstance(value, typing.Mapping):
            items = value
        elif isinstance(value, typing.Iterable):
            items = dict(zip(fields, typing.cast("typing.Iterable[object]", value)))
        else:
            raise TypeError(f"Expected iterable, got {type(value)}")

        items = await model._validate_universal(items)

        if hasattr(tup, "_fields"):
            return tup(**items)
        else:
            tp = typing.get_origin(tup) or tup
            return tp(tuple(items.values()))

    if model.isasync:
        return as_validator(validator.asynchronous)
    else:
        return as_validator(validator.synchronous)


@debuggable_deco
def typeddict_validator(typeddict: typing.Type[typing.TypedDict]) -> AnnotationValidator:
    """Validate a typeddict."""
    required: typing.Collection[str] = getattr(typeddict, "__required_keys__", ())
    definitions = {
        name: (tp if required and name in required else (tp, None)) for name, tp in typeddict.__annotations__.items()
    }
    model = apimodel.create_model(typeddict.__name__, **definitions)

    @utility.as_universal
    async def validator(root: apimodel.APIModel, value: object) -> object:
        if not isinstance(value, typing.Mapping):
            raise TypeError(f"Expected mapping, got {type(value)}")

        value = typing.cast("typing.Mapping[str, object]", value)

        return await model._validate_universal(value)

    if model.isasync:
        return as_validator(validator.asynchronous)
    else:
        return as_validator(validator.synchronous)


RAW_VALIDATORS: typing.Mapping[object, AnnotationValidator] = {
    int: cast_validator(int),
    float: cast_validator(float),
    str: cast_validator(str),
    bytes: cast_validator(bytes),
    bool: cast_validator(bool),
    datetime.datetime: datetime_validator,
    datetime.timedelta: timedelta_validator,
    object: noop_validator,
    None: literal_validator([None]),
    type(None): literal_validator([None]),
}

if not typing.TYPE_CHECKING:
    for tp, validator in RAW_VALIDATORS.items():
        validator.tp = tp


def normalize_annotation(tp: object) -> object:
    """Normalize an annotation and remove aliases."""
    if tp is type(None):  # noqa: E721
        tp = None

    if isinstance(tp, tutils.AnnotatedAlias):
        tp = tp.__metadata__[0] if tp.__metadata__ else tp.__origin__  # type: ignore # compatibility with 3.8

    if isinstance(tp, typing.TypeVar):
        if tp.__bound__:
            tp = tp.__bound__
        elif tp.__constraints__:
            tp = typing.Union[tp.__constraints__]  # type: ignore
        else:
            tp = object

    if typing.get_origin(tp) in tutils.UnionTypes:
        if len(args := typing.get_args(tp)) == 1:
            tp = normalize_annotation(args[0])

    return tp


def _add_tp(callback: tutils.CallableT) -> tutils.CallableT:
    def wrapper(tp: object, *args: object, **kwargs: object) -> object:
        tp = normalize_annotation(tp)
        r = callback(tp, *args, **kwargs)
        assert isinstance(r, AnnotationValidator)
        r.tp = tp

        return r

    return typing.cast("tutils.CallableT", wrapper)


@_add_tp
def get_validator(tp: object) -> AnnotationValidator:
    """Get a validator for the given type."""
    # TODO: pydantic and dataclasses

    origin = typing.get_origin(tp) or tp
    args = typing.get_args(tp)

    # TODO any other forms of unions?
    if origin in tutils.UnionTypes:
        validators = [get_validator(arg) for arg in args]
        return union_validator(validators)

    if validator := RAW_VALIDATORS.get(tp):
        return validator

    if tutils.lenient_issubclass(origin, enum.Enum):
        return enum_validator(origin)

    if tutils.lenient_issubclass(origin, apimodel.APIModel):
        return model_validator(origin)
    if tutils.lenient_issubclass(origin, tuple) and (not args or args[-1] != ...):
        return tuple_validator(typing.cast("type[tuple[object, ...]]", tp))
    if tutils.lenient_issubclass(origin, dict) and hasattr(origin, "__annotations__"):
        return typeddict_validator(typing.cast("type[typing.TypedDict]", tp))

    if tutils.lenient_issubclass(origin, typing.Mapping):
        key_validator = get_validator(args[0]) if args else noop_validator
        value_validator = get_validator(args[1]) if args else noop_validator
        return mapping_validator(origin, key_validator, value_validator)
    if tutils.lenient_issubclass(origin, typing.Collection):
        validator = get_validator(args[0]) if args else noop_validator
        return collection_validator(origin, validator)

    if origin == typing.Literal:
        return literal_validator(args)

    if isinstance(tp, type):
        if validator := getattr(tp, "__validator__", None):
            return AnnotationValidator(validator)

        return arbitrary_validator(tp)

    raise TypeError(f"Unknown annotation: {tp!r}. Use Annotated[{tp!r}, object] to disable the default validator.")


async def cast(tp: typing.Type[T], value: object) -> T:
    """Cast the value to the given type."""
    validator = get_validator(tp)
    return await validator(apimodel.APIModel({}), value)


def cast_sync(tp: typing.Type[T], value: object) -> T:
    """Cast the value to the given type synchronously."""
    validator = get_validator(tp)
    return validator.synchronous(apimodel.APIModel({}), value)


def validate_arguments(callback: typing.Callable[..., T]) -> typing.Callable[..., T]:
    """Validate arguments of a function.

    Inspired by pydantic. Positional-only arguments are not supported because just no.
    """
    signature = inspect.signature(callback)

    type_hints = typing.get_type_hints(callback)
    validators = {name: get_validator(annotation) for name, annotation in type_hints.items()}

    @functools.wraps(callback)
    def wrapper(*args: object, **kwargs: object) -> object:
        model = apimodel.APIModel({})

        bound = signature.bind(*args, **kwargs)
        kwargs = {
            name: validator.synchronous(model, bound.arguments[name])
            for name, validator in validators.items()
            if name in bound.arguments
        }

        r = callback(**kwargs)
        if "return" in validators:
            r = validators["return"].synchronous(model, r)

        return r

    return typing.cast("typing.Callable[..., T]", wrapper)
