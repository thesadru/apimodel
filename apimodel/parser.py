"""Parser functions for various types."""
from __future__ import annotations

import datetime
import enum
import functools
import inspect
import types
import typing
from unittest.mock import _Call as Call

from . import apimodel, errors, tutils, utility, validation

__all__ = ["acast", "cast", "get_validator", "validate_arguments"]

T = typing.TypeVar("T")


class AnnotationValidator(validation.Validator):
    """Special validator for annotations."""

    __slots__ = ("tp", "_isasync")

    tp: object

    def __init__(self, callback: tutils.AnyCallable, *, isasync: bool = False) -> None:
        """Initialize an AnnotationValidator.

        The callback must have an annotated return type.
        """
        super().__init__(callback, order=validation.Order.ANNOTATION)
        self._isasync = isasync

        try:
            self.tp = typing.get_type_hints(callback)["return"]
        except Exception:
            self.tp = object

    def __repr_args__(self) -> typing.Mapping[str, object]:
        return {"callback": self.callback}

    @property
    def isasync(self) -> bool:
        return self._isasync


def as_validator(callback: tutils.ValidatorSig, *, isasync: bool = False) -> AnnotationValidator:
    """Convert a validator function to a validator class."""
    signature = inspect.signature(callback)
    validator = AnnotationValidator(callback, isasync=isasync)
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

        if inspect.isfunction(callback):
            call = Call((func.__name__, args, kwargs))
            notation = repr(call)[5:]
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
def literal_validator(*args: object) -> AnnotationValidator:
    """Check if the value is one of the given literals."""
    values = set(args)

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
    # 3.11 introduces ReprEnum which messes with the mro so we must walk through it
    tp = object
    for superclass in enum_type.__mro__:
        if superclass is not object and not tutils.lenient_issubclass(superclass, enum.Enum):
            tp = superclass
            break

    try:
        inner_validator = get_validator(tp)
    except Exception:
        inner_validator = noop_validator

    async def validator(model: apimodel.APIModel, value: object) -> object:
        value = await inner_validator(model, value)
        return typing.cast("enum.Enum", enum_type(value))

    return as_validator(validator, isasync=inner_validator.isasync)


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

    async def validator(model: apimodel.APIModel, value: object) -> typing.Collection[object]:
        if not tutils.generic_isinstance(value, typing.Iterable[object]):
            raise TypeError(f"Expected iterable, got {type(value)}")

        value = value

        items: typing.Collection[object] = []

        with errors.catch_errors(model) as catcher:
            for index, item in enumerate(value):
                with catcher.catch(loc=index):
                    items.append((await inner_validator(model, item)))

        return collection_type(items)

    return as_validator(validator, isasync=inner_validator.isasync)


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

    async def validator(model: apimodel.APIModel, value: object) -> object:
        if not tutils.generic_isinstance(value, typing.Mapping[object, object]):
            raise TypeError(f"Expected mapping, got {type(value)}")

        mapping: typing.Mapping[object, object] = {}

        with errors.catch_errors(model) as catcher:
            for key in value:
                with catcher.catch(loc=str(key)):
                    mapping[(await key_validator(model, key))] = await value_validator(model, value[key])

        return mapping_type(mapping)

    return as_validator(validator, isasync=key_validator.isasync or value_validator.isasync)


@debuggable_deco
def union_validator(*validators: validation.Validator) -> AnnotationValidator:
    """Return the first successful validator."""
    if len(validators) == 1:
        validator = validators[0]
        if isinstance(validator, AnnotationValidator):
            return validator

        return as_validator(validator.callback)

    # shift None to the start
    new_validators = tuple(
        validator
        for validator in validators
        if isinstance(validator, AnnotationValidator) and validator.tp not in tutils.NoneTypes
    )
    if len(validators) != len(new_validators):
        validators = (RAW_VALIDATORS[None],) + new_validators

    del new_validators

    async def validator(model: apimodel.APIModel, value: object) -> object:
        catcher = errors.ErrorCatcher(model)
        for index, validator in enumerate(validators):
            with catcher.catch(loc=f"Union[{index}]"):
                return await validator(model, value)

        catcher.raise_errors()

    return as_validator(validator, isasync=any(validator.isasync for validator in validators))


@debuggable_deco
def model_validator(model: typing.Type[apimodel.APIModel]) -> AnnotationValidator:
    """Validate a model."""
    origin = typing.get_origin(model)
    if origin is not None:
        model = typing.cast("type[apimodel.APIModel]", types.new_class(origin.__name__, (model,)))

    async def validator(root: apimodel.APIModel, value: object) -> object:
        if isinstance(value, model):
            return value

        return await model.create(value, **root.get_extras())

    return as_validator(validator, isasync=model.isasync)


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

    async def validator(value: object) -> typing.Tuple[object, ...]:
        items: typing.Mapping[str, object]

        if tutils.generic_isinstance(value, typing.Mapping[str, object]):
            items = value
        elif tutils.generic_isinstance(value, typing.Iterable[object]):
            items = dict(zip(fields, value))
        else:
            raise TypeError(f"Expected iterable, got {type(value)}")

        items = await model.validate(items)

        if hasattr(tup, "_fields"):
            return tup(**items)
        else:
            tp = typing.get_origin(tup) or tup
            return tp(tuple(items.values()))

    return as_validator(validator, isasync=model.isasync)


@debuggable_deco
def typeddict_validator(typeddict: typing.Type[typing.TypedDict]) -> AnnotationValidator:
    """Validate a typeddict."""
    required: typing.Collection[str] = getattr(typeddict, "__required_keys__", ())
    definitions = {
        name: (tp if required and name in required else (tp, None)) for name, tp in typeddict.__annotations__.items()
    }
    model = apimodel.create_model(typeddict.__name__, **definitions)

    async def validator(value: object) -> object:
        if not isinstance(value, typing.Mapping):
            raise TypeError(f"Expected mapping, got {type(value)}")

        value = typing.cast("typing.Mapping[str, object]", value)

        return await model.validate(value)

    return as_validator(validator, isasync=model.isasync)


RAW_VALIDATORS: typing.Mapping[object, AnnotationValidator] = {
    int: cast_validator(int),
    float: cast_validator(float),
    str: cast_validator(str),
    bytes: cast_validator(bytes),
    bool: cast_validator(bool),
    datetime.datetime: datetime_validator,
    datetime.timedelta: timedelta_validator,
    object: noop_validator,
    None: literal_validator(None),
    type(None): literal_validator(None),
}

if not typing.TYPE_CHECKING:
    for tp, validator in RAW_VALIDATORS.items():
        validator.tp = tp


def resolve_typevar(tp: typing.TypeVar, *, model: typing.Optional[type] = None) -> object:
    if model is not None:
        typevars = utility.resolve_typevars(model)
        if tp.__name__ not in typevars:
            raise TypeError(f"Undeclared typevar used: {tp}")

        if not isinstance(typevars[tp.__name__], typing.TypeVar):
            return typevars[tp.__name__]

    if tp.__constraints__:
        return typing.Union[tp.__constraints__]  # type: ignore
    elif tp.__bound__:
        return tp.__bound__
    else:
        return object


def _add_tp(callback: tutils.CallableT) -> tutils.CallableT:
    def wrapper(tp: object, *args: object, **kwargs: object) -> object:
        if isinstance(tp, tutils.AnnotatedAlias):
            tp = tp.__metadata__[0] if tp.__metadata__ else tp.__origin__  # type: ignore # compatibility with 3.8

        r = callback(tp, *args, **kwargs)
        assert isinstance(r, AnnotationValidator)
        r.tp = tp

        return r

    return typing.cast("tutils.CallableT", wrapper)


@_add_tp
def get_validator(tp: object, *, model: typing.Optional[type] = None) -> AnnotationValidator:
    """Get a validator for the given type."""
    # TODO: pydantic and dataclasses
    if isinstance(tp, typing.TypeVar):
        tp = resolve_typevar(tp, model=model)

    origin = typing.get_origin(tp) or tp
    args = typing.get_args(tp)

    if origin in tutils.UnionTypes:
        validators = [get_validator(arg, model=model) for arg in args]
        return union_validator(*validators)

    if validator := RAW_VALIDATORS.get(tp):
        return validator

    if tutils.lenient_issubclass(origin, enum.Enum):
        return enum_validator(origin)

    if tutils.lenient_issubclass(origin, apimodel.APIModel):
        return model_validator(typing.cast("type[apimodel.APIModel]", tp))
    if tutils.lenient_issubclass(origin, tuple) and (not args or args[-1] != ...):
        return tuple_validator(typing.cast("type[tuple[object, ...]]", tp))
    if tutils.lenient_issubclass(origin, dict) and hasattr(origin, "__annotations__"):
        return typeddict_validator(typing.cast("type[typing.TypedDict]", tp))

    if tutils.lenient_issubclass(origin, typing.Mapping):
        key_validator = get_validator(args[0], model=model) if args else noop_validator
        value_validator = get_validator(args[1], model=model) if args else noop_validator
        return mapping_validator(origin, key_validator, value_validator)
    if tutils.lenient_issubclass(origin, typing.Collection):
        validator = get_validator(args[0], model=model) if args else noop_validator
        return collection_validator(origin, validator)

    if origin == typing.Literal:
        return literal_validator(*args)

    if isinstance(tp, type):
        if validator := getattr(tp, "__validator__", None):
            return AnnotationValidator(validator)

        return arbitrary_validator(tp)

    raise TypeError(f"Unknown annotation: {tp!r}. Use Annotated[{tp!r}, object] to disable the default validator.")


# sync is the default since typing.cast() is synchronous too
# it'd be rare to see a synchronous usage for cast


@utility.as_universal
async def acast(tp: typing.Type[T], value: object) -> T:
    """Cast the value to the given type asynchronously."""
    validator = get_validator(tp)
    return await validator(apimodel.APIModel({}), value)


def cast(tp: typing.Type[T], value: object) -> T:
    """Cast the value to the given type synchronously."""
    return acast.synchronous(tp, value)  # type: ignore # issues with comprehending TypeVar


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
