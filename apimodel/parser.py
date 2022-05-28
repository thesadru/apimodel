"""Parser functions for various types."""
from __future__ import annotations

import asyncio
import datetime
import inspect
import typing
from unittest.mock import _Call as Call

from . import apimodel, tutils, utility, validation

__all__ = ["cast", "get_validator"]


class AnnotationValidator(validation.Validator):
    """Special validator for annotations."""

    __slots__ = ("tp",)

    tp: typing.Any

    def __init__(self, callback: tutils.AnyCallable) -> None:
        super().__init__(callback, order=validation.Order.ANNOTATION)

        try:
            self.tp = typing.get_type_hints(callback)["return"]
        except Exception:
            self.tp = typing.Any

    def __repr_args__(self) -> typing.Mapping[str, typing.Any]:
        return {"callback": self.callback, "tp": self.tp}


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
            if inspect.ismethod(callback):
                if isinstance(callback.__self__, utility.UniversalAsync):
                    callback = callback.__self__.callback
                else:
                    return

            call = Call((func.__name__, args, kwargs))
            notation = repr(call)[5:]
            if asyncio.iscoroutinefunction(obj):
                notation = "async " + notation

            callback.__qualname__ = notation

        return obj

    return typing.cast("tutils.AnyCallableT", wrapper)


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
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)

    return value.astimezone(datetime.timezone.utc)


@as_validator
def timedelta_validator(value: typing.Union[str, int, float]) -> datetime.timedelta:
    """Parse a timedelta."""
    # TODO: Support ISO8601
    if isinstance(value, datetime.timedelta):
        return value

    value = float(value)
    return datetime.timedelta(seconds=value)


@as_validator
def noop_validator(value: typing.Any) -> typing.Any:
    """Return the value."""
    return value


@debuggable_deco
def cast_validator(callback: typing.Callable[[typing.Any], typing.Any]) -> AnnotationValidator:
    """Cast the value to the given type."""

    @as_validator
    def validator(value: typing.Any) -> typing.Any:
        return callback(value)

    return validator


@debuggable_deco
def arbitrary_validator(tp: typing.Type[typing.Any]) -> AnnotationValidator:
    """Expect a specific type of value."""

    @as_validator
    def validator(value: typing.Any) -> typing.Any:
        if isinstance(value, tp):
            return value

        raise TypeError(f"Expected {tp}, got {value}")

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


# TODO: async item validators
@debuggable_deco
def collection_validator(
    collection_type: typing.Callable[[typing.Collection[typing.Any]], typing.Collection[typing.Any]],
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

    @as_validator
    def validator(model: apimodel.APIModel, value: typing.Any) -> typing.Collection[typing.Any]:
        items: typing.Collection[typing.Any] = []

        for item in value:
            items.append(inner_validator(model, item))

        return collection_type(items)

    return validator


@debuggable_deco
def mapping_validator(
    mapping_type: typing.Callable[[typing.Mapping[typing.Any, typing.Any]], typing.Mapping[typing.Any, typing.Any]],
    key_validator: validation.Validator,
    value_validator: validation.Validator,
) -> AnnotationValidator:
    """Validate the keys and values of a mapping."""
    mapping_type = typing.get_origin(mapping_type) or mapping_type

    if inspect.isabstract(mapping_type):
        mapping_type = dict

    @as_validator
    def validator(model: apimodel.APIModel, value: typing.Any) -> typing.Collection[typing.Any]:
        mapping: typing.Mapping[typing.Any, typing.Any] = {}

        for key in value:
            mapping[key_validator(model, key)] = value_validator(model, value[key])

        return mapping_type(mapping)

    return validator


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
    def validator(model: apimodel.APIModel, value: typing.Any) -> tutils.UniversalAsyncGenerator[typing.Any]:
        errors: typing.List[Exception] = []

        for validator in validators:
            try:
                x = yield validator(model, value)
            except (ValueError, TypeError) as e:
                errors.append(e)
            else:
                return x

        raise errors[0]

    if any(validator.isasync for validator in validators):
        return as_validator(validator.asynchronous)
    else:
        return as_validator(validator.synchronous)


@debuggable_deco
def model_validator(model: typing.Type[apimodel.APIModel]) -> AnnotationValidator:
    """Validate a model."""

    @as_validator
    def sync_validator(root: apimodel.APIModel, value: typing.Any) -> typing.Any:
        if isinstance(value, model):
            return value

        return model.sync_create(value, **root.get_extras())

    @as_validator
    async def async_validator(root: apimodel.APIModel, value: typing.Any) -> typing.Any:
        if isinstance(value, model):
            return value

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
    bool: cast_validator(bool),
    datetime.datetime: datetime_validator,
    datetime.timedelta: timedelta_validator,
    typing.Any: noop_validator,
    None: literal_validator([None]),
    type(None): literal_validator([None]),
}

if not typing.TYPE_CHECKING:
    for tp, validator in RAW_VALIDATORS.items():
        validator.tp = tp


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
    # TODO: pydantic and dataclasses

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

    if isinstance(tp, type):
        return arbitrary_validator(tp)

    raise TypeError(f"Unknown annotation: {tp}. Use Annotated[{tp}, typing.Any] to disable the default validator.")


def cast(tp: typing.Any, value: typing.Any) -> typing.Any:
    """Cast the value to the given type."""
    validator = get_validator(tp)
    return validator(apimodel.APIModel({}), value)
