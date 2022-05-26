"""Parser functions for various types."""
from __future__ import annotations

import asyncio
import datetime
import inspect
import typing
from unittest.mock import _Call as Call

from . import apimodel, tutils, validation

__all__ = ["cast", "get_validator"]


class AnnotationValidator(validation.Validator):
    """Special validator for annotations."""

    def __init__(self, callback: tutils.AnyCallable) -> None:
        super().__init__(callback, order=validation.Order.ANNOTATION)

    def __repr_args__(self) -> typing.Mapping[str, typing.Any]:
        return {"callback": self.callback}


def as_validator(callback: tutils.ValidatorSig) -> AnnotationValidator:
    """Convert a validator function to a validator class."""
    signature = inspect.signature(callback)
    validator = AnnotationValidator(callback)
    if len(signature.parameters) >= 2:
        validator.bound = True

    return validator


def debuggable_deco(func: tutils.AnyCallableT) -> tutils.AnyCallableT:
    """Make a higher order function's return debuggable."""

    def wrapper(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        obj = func(*args, **kwargs)
        if callable(obj):
            callback = obj
            if isinstance(obj, validation.Validator):
                callback = obj.callback

            call = Call((func.__name__, args, kwargs))
            notation = repr(call)[5:]
            if asyncio.iscoroutinefunction(obj):
                notation = "async " + notation

            callback.__qualname__ = notation

        return obj

    return typing.cast("tutils.AnyCallableT", wrapper)


@as_validator
def noop_validator(value: typing.Any) -> typing.Any:
    """Return the value."""
    return value


@debuggable_deco
def union_validator(validators: typing.Sequence[validation.Validator]) -> AnnotationValidator:
    """Return the first successful validator."""

    @as_validator
    def sync_validator(model: apimodel.APIModel, value: typing.Any) -> typing.Any:
        errors: typing.List[Exception] = []

        for validator in validators:
            try:
                x = validator(model, value)
            except (ValueError, TypeError) as e:
                errors.append(e)
            else:
                return x

        # TODO tracebackable
        raise errors[0]

    @as_validator
    async def async_validator(model: apimodel.APIModel, value: typing.Any) -> typing.Any:
        errors: typing.List[Exception] = []

        for validator in validators:
            try:
                x = validator(model, value)
            except (ValueError, TypeError) as e:
                errors.append(e)
            else:
                return x

        raise errors[0]

    if any(validator.isasync for validator in validators):
        return async_validator
    else:
        return sync_validator


@debuggable_deco
def cast_validator(callback: typing.Callable[[typing.Any], typing.Any]) -> AnnotationValidator:
    """Cast the value to the given type."""

    @as_validator
    def validator(value: typing.Any) -> typing.Any:
        return callback(value)

    return validator


@debuggable_deco
def literal_validator(values: typing.Collection[typing.Any]) -> AnnotationValidator:
    """Check if the value is one of the given literals."""
    values = set(values)

    @as_validator
    def validator(value: typing.Any) -> typing.Any:
        if value in values:
            return value

        raise TypeError(f"Invalid value, must be one of: {values}")

    return validator


@debuggable_deco
def collection_validator(
    sequence_type: typing.Callable[[typing.Collection[typing.Any]], typing.Collection[typing.Any]],
    inner_validator: validation.Validator,
) -> AnnotationValidator:
    """Validate the items of a collection."""
    if inspect.isabstract(sequence_type):
        if tutils.lenient_issubclass(sequence_type, typing.MutableSequence):
            sequence_type = list
        elif tutils.lenient_issubclass(sequence_type, typing.MutableSet):
            sequence_type = set
        elif tutils.lenient_issubclass(sequence_type, typing.Set):
            sequence_type = frozenset
        else:
            sequence_type = tuple

    @as_validator
    def validator(model: apimodel.APIModel, value: typing.Any) -> typing.Collection[typing.Any]:
        items: typing.Collection[typing.Any] = []

        for item in value:
            items.append(inner_validator(model, item))

        return sequence_type(items)

    return validator


@debuggable_deco
def mapping_validator(
    mapping_type: typing.Callable[[typing.Mapping[typing.Any, typing.Any]], typing.Mapping[typing.Any, typing.Any]],
    key_validator: validation.Validator,
    value_validator: validation.Validator,
) -> AnnotationValidator:
    """Validate the keys and values of a mapping."""
    if inspect.isabstract(mapping_type):
        mapping_type = dict

    @as_validator
    def validator(model: apimodel.APIModel, value: typing.Any) -> typing.Collection[typing.Any]:
        mapping: typing.Mapping[typing.Any, typing.Any] = {}

        for key in value:
            mapping[key_validator(model, key)] = value_validator(model, value[key])

        return mapping_type(mapping)

    return validator


@as_validator
def datetime_validator(value: typing.Union[datetime.datetime, str, int, float]) -> datetime.datetime:
    """Parse a datetime."""
    if isinstance(value, datetime.datetime):
        return value

    try:
        value = float(value)
    except ValueError:
        pass

    if isinstance(value, (int, float)):
        # attempt to parse unix

        # if a number is this large it must be in milliseconds/microseconds
        while abs(value) > 2e10:
            value /= 1000

        return datetime.datetime.fromtimestamp(value, tz=datetime.timezone.utc)

    # unsupported by the builtin parser
    value = value.rstrip("Z")
    value = datetime.datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)

    return value


@as_validator
def timedelta_validator(value: typing.Union[str, int, float]) -> datetime.timedelta:
    """Parse a timedelta."""
    # TODO: Support ISO8601
    if isinstance(value, datetime.timedelta):
        return value

    value = float(value)
    return datetime.timedelta(seconds=value)


@debuggable_deco
def model_validator(model: typing.Type[apimodel.APIModel]) -> AnnotationValidator:
    """Validate a model."""
    # TODO root fields
    @as_validator
    def sync_validator(root: apimodel.APIModel, value: typing.Any) -> typing.Any:
        return model.sync_create(value, **root.get_extras())

    @as_validator
    async def async_validator(root: apimodel.APIModel, value: typing.Any) -> typing.Any:
        return await model.create(value, **root.get_extras())

    if model.isasync:
        return async_validator
    else:
        return sync_validator


RAW_VALIDATORS: typing.Mapping[typing.Any, AnnotationValidator] = {
    int: cast_validator(int),
    float: cast_validator(float),
    str: cast_validator(str),
    bytes: cast_validator(bytes),
    datetime.datetime: datetime_validator,
    datetime.timedelta: timedelta_validator,
    typing.Any: noop_validator,
    None: literal_validator([None]),
    type(None): literal_validator([None]),
}


def normalize_annotation(tp: typing.Any) -> typing.Any:
    if isinstance(tp, tutils.AnnotatedAlias):
        tp = typing.get_args(tp)[1]

    if isinstance(tp, typing.TypeVar):
        if tp.__bound__:
            tp = tp.__bound__
        elif tp.__constraints__:
            tp = typing.Union[tp.__constraints__]  # type: ignore
        else:
            tp = typing.Any

    if typing.get_origin(tp) in tutils.UnionTypes:
        if len(args := typing.get_args(tp)) == 1:
            tp = args[0]

    return tp


def get_validator(tp: typing.Any, *, normalize: bool = True) -> AnnotationValidator:
    """Get a validator for the given type."""
    # TODO: NamedTuple and TypedDict

    if normalize:
        tp = normalize_annotation(tp)

    origin = typing.get_origin(tp) or tp
    args = typing.get_args(tp)

    # TODO any other forms of unions?
    if origin in tutils.UnionTypes:
        validators = [get_validator(arg) for arg in args]
        return union_validator(validators)

    if validator := RAW_VALIDATORS.get(tp):
        return validator

    if tutils.lenient_issubclass(origin, apimodel.APIModel):
        return model_validator(tp)

    if tutils.lenient_issubclass(origin, typing.Mapping):
        key_validator = get_validator(args[0]) if args else noop_validator
        value_validator = get_validator(args[1]) if args else noop_validator
        return mapping_validator(origin, key_validator, value_validator)

    if tutils.lenient_issubclass(origin, typing.Collection):
        validator = get_validator(args[0]) if args else noop_validator
        return collection_validator(origin, validator)

    if origin == typing.Literal:
        return literal_validator(args)

    return cast_validator(tp)


def cast(tp: typing.Any, value: typing.Any) -> typing.Any:
    """Cast the value to the given type."""
    validator = get_validator(tp)
    return validator(apimodel.APIModel({}), value)
