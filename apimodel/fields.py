"""Field descriptors."""
from __future__ import annotations

import typing

from . import parser, tutils, utility, validation

if typing.TYPE_CHECKING:
    import typing_extensions

__all__ = ["Extra", "ExtraInfo", "Field", "FieldInfo", "ModelFieldInfo"]

T = typing.TypeVar("T")


# TODO: default_factory
class FieldInfo(utility.Representation):
    """Basic information about a field."""

    __slots__ = ("default", "name", "private", "validators", "extra")

    default: object
    """The default value of the field."""

    name: typing.Optional[str]
    """Key name in the JSON object. Similar to pydantic's alias.

    The attribute name by default
    """

    private: typing.Optional[bool]
    """Whether the field is private. Affects model.as_dict()

    Set to True by default if the attribute name starts with an underscore.
    """

    validators: typing.List[validation.Validator]
    """Validators for the value."""

    extra: typing.Mapping[str, typing.Any]
    """Extra metadata about the field.

    May be used by subclasses to store additional information.
    """

    def __init__(
        self,
        default: object = ...,
        *,
        name: typing.Optional[str] = None,
        private: typing.Optional[bool] = False,
        validators: tutils.MaybeSequence[tutils.AnyCallable] = (),
        **extra: typing.Any,
    ) -> None:
        """Initialize a FieldInfo.

        Extra arguments may be repurposed for subclass attributes.
        """
        self.default = default
        self.name = name
        self.private = private
        self.extra = extra

        self.validators = [
            callback if isinstance(callback, validation.Validator) else validation.Validator(callback)
            for callback in utility.flatten_sequences(validators)
        ]
        self.validators.sort(key=lambda v: v.order)

    def add_validators(self, *validators: validation.Validator) -> None:
        """Properly add validators to the field."""
        self.validators += validators
        self.validators.sort(key=lambda v: v.order)


class ModelFieldInfo(FieldInfo):
    """Complete information about a field."""

    __slots__ = ()

    name: str
    private: bool

    @classmethod
    def from_annotation(cls, name: str, annotation: object, default: object = ...) -> typing_extensions.Self:
        """Create a new model field info from an annotation.

        If the default is already a FieldInfo, the data is copied.
        """
        validators: typing.Sequence[validation.Validator] = []
        private: bool = name[0] == "_"
        extra: typing.Mapping[str, typing.Any] = {}

        if isinstance(default, FieldInfo):
            name = default.name or name
            private = default.private if default.private is not None else private
            extra = default.extra
            validators.extend(default.validators)

            default = default.default

        # not done by default on newer version of python
        if default is None:
            try:
                annotation = typing.Optional[annotation]  # type: ignore
            except Exception:
                pass

        validator = parser.get_validator(annotation)
        validators.append(validator)

        return cls(default, name=name, private=private, validators=validators, **extra)

    @property
    def annotation_validator(self) -> parser.AnnotationValidator:
        """Return the validator for the annotation."""
        return next(validator for validator in self.validators if isinstance(validator, parser.AnnotationValidator))

    @property
    def tp(self) -> object:
        """Return the type of the field."""
        return self.annotation_validator.tp


class ExtraInfo(utility.Representation):
    """Descriptor for a special extra attribute."""

    __slots__ = ("default", "name")

    default: object
    name: str

    def __init__(self, default: object = ..., name: str = "") -> None:
        """Initialize an ExtraInfo."""
        self.default = default
        self.name = name


@typing.overload
def Field(
    default: T,
    *,
    name: typing.Optional[str] = ...,
    private: typing.Optional[bool] = ...,
    validator: tutils.MaybeSequence[tutils.AnyCallable] = ...,
    validators: tutils.MaybeSequence[tutils.AnyCallable] = ...,
    **extra: typing.Any,
) -> T | typing.Any:
    ...


@typing.overload
def Field(
    *,
    name: typing.Optional[str] = ...,
    private: typing.Optional[bool] = ...,
    validator: tutils.MaybeSequence[tutils.AnyCallable] = ...,
    validators: tutils.MaybeSequence[tutils.AnyCallable] = ...,
    **extra: typing.Any,
) -> typing.Any:
    ...


def Field(
    default: object = ...,
    *,
    name: typing.Optional[str] = None,
    private: typing.Optional[bool] = None,
    validator: tutils.MaybeSequence[tutils.AnyCallable] = (),
    validators: tutils.MaybeSequence[tutils.AnyCallable] = (),
    **extra: typing.Any,
) -> typing.Any:
    """Create a new FieldInfo."""
    return FieldInfo(
        default=default,
        name=name,
        private=private,
        validators=utility.flatten_sequences(validator, validators),
        **extra,
    )


def Extra(default: object = ..., name: str = "") -> typing.Any:
    """Create a new ExtraInfo."""
    return ExtraInfo(default, name=name)
