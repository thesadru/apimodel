"""Parser functions for various types."""
from __future__ import annotations

import asyncio
import datetime
import functools
import inspect
import typing
from unittest.mock import _Call as Call

from . import apimodel, tutils, utility, validation

__all__ = ["cast", "get_validator", "validate_arguments"]

T = typing.TypeVar("T")


class AnnotationValidator(validation.Validator):
    """Special validator for annotations."""

    __slots__ = ("tp",)

    tp: object

    def __init__(self, callback: tutils.AnyCallable) -> None:
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


def debuggable_deco(func: tutils.AnyCallableT) -> tutils.AnyCallableT:
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

        raise TypeError(f"Invalid value, must be one of: {values}")

    return validator


# TODO: async item validators
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

    @as_validator
    def validator(model: apimodel.APIModel, value: object) -> typing.Collection[object]:
        if not isinstance(value, typing.Iterable):
            raise TypeError(f"Expected iterable, got {type(value)}")

        value = typing.cast("typing.Iterable[object]", value)

        items: typing.Collection[object] = []

        for item in value:
            items.append(inner_validator(model, item))

        return collection_type(items)

    return validator


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

    @as_validator
    def validator(model: apimodel.APIModel, value: object) -> typing.Collection[object]:
        if not isinstance(value, typing.Mapping):
            raise TypeError(f"Expected mapping, got {type(value)}")

        value = typing.cast("typing.Mapping[object, object]", value)

        mapping: typing.Mapping[object, object] = {}

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
    def validator(model: apimodel.APIModel, value: object) -> tutils.UniversalAsyncGenerator[object]:
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
        tp = typing.get_args(tp)[0]

    if isinstance(tp, typing.TypeVar):
        if tp.__bound__:
            tp = tp.__bound__
        elif tp.__constraints__:
            tp = typing.Union[tp.__constraints__]  # type: ignore
        else:
            tp = object

    if typing.get_origin(tp) in tutils.UnionTypes:
        if len(args := typing.get_args(tp)) == 1:
            tp = args[0]

    return tp


def _add_tp(callback: tutils.AnyCallableT) -> tutils.AnyCallableT:
    def wrapper(tp: object, *args: object, **kwargs: object) -> object:
        tp = normalize_annotation(tp)
        r = callback(tp, *args, **kwargs)
        assert isinstance(r, AnnotationValidator)
        r.tp = tp

        return r

    return typing.cast("tutils.AnyCallableT", wrapper)


@_add_tp
def get_validator(tp: object) -> AnnotationValidator:
    """Get a validator for the given type."""
    # TODO: NamedTuple and TypedDict
    # TODO: pydantic and dataclasses

    origin = typing.get_origin(tp) or tp
    args = typing.get_args(tp)

    # TODO any other forms of unions?
    if origin in tutils.UnionTypes:
        validators = [get_validator(arg) for arg in args]
        return union_validator(validators)

    if validator := RAW_VALIDATORS.get(tp):
        return validator

    if tutils.lenient_issubclass(origin, apimodel.APIModel):
        return model_validator(origin)

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

    raise TypeError(f"Unknown annotation: {tp}. Use Annotated[object, {tp}] to disable the default validator.")


def cast(tp: object, value: object) -> object:
    """Cast the value to the given type."""
    validator = get_validator(tp)
    return validator(apimodel.APIModel({}), value)


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
            name: validator(model, bound.arguments[name])
            for name, validator in validators.items()
            if name in bound.arguments
        }

        r = callback(**kwargs)
        if "return" in validators:
            r = validators["return"](model, r)

        return r

    return typing.cast("typing.Callable[..., T]", wrapper)
