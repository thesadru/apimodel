"""Field descriptors."""
from __future__ import annotations

import typing

from . import parser, tutils, utility, validation

__all__ = ["Aliased", "Extra", "ExtraInfo", "Field", "FieldInfo", "ModelFieldInfo", "NamedProperty", "named_property"]

T = typing.TypeVar("T")


# TODO: default_factory
class FieldInfo(utility.Representation):
    """Basic information about a field."""

    __slots__ = ("default", "default_factory", "alias", "private", "validators", "extra")

    default: object
    """The default value of the field."""

    default_factory: typing.Optional[typing.Callable[[], object]]
    """Factory for the default value in case of mutables."""

    alias: typing.Optional[str]
    """Key name in the JSON object. Similar to pydantic's alias.

    The attribute name by default.
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
        default_factory: typing.Optional[typing.Callable[[], object]] = None,
        alias: typing.Optional[str] = None,
        private: typing.Optional[bool] = False,
        validators: tutils.MaybeSequence[tutils.AnyCallable] = (),
        **extra: typing.Any,
    ) -> None:
        """Initialize a FieldInfo.

        Extra arguments may be repurposed for subclass attributes.
        """
        self.default = default
        self.default_factory = default_factory
        self.alias = alias
        self.private = private
        self.extra = extra

        self.validators = []
        self.add_validators(*utility.flatten_sequences(validators))

    def add_validators(self, *validators: typing.Union[validation.Validator, tutils.AnyCallable]) -> None:
        """Properly add validators to the field."""
        for callback in validators:
            if isinstance(callback, validation.Validator):
                self.validators.append(callback)
            else:
                self.validators.append(validation.Validator(callback))

        self.validators.sort(key=lambda v: v.order)

    def _get_default(self) -> object:
        """Get the default value of the field.

        Returns Ellipsis if not available.
        """
        if self.default_factory is not None:
            return self.default_factory()

        return self.default


class ModelFieldInfo(FieldInfo):
    """Complete information about a field."""

    __slots__ = ()

    alias: str
    private: bool

    @classmethod
    def from_annotation(
        cls,
        name: str,
        annotation: object,
        default: object = ...,
        *,
        model: typing.Optional[type] = None,
    ) -> tutils.Self:
        """Create a new model field info from an annotation.

        If the default is already a FieldInfo, the data is copied.
        """
        default_factory: typing.Optional[typing.Callable[[], object]] = None
        validators: typing.Sequence[validation.Validator] = []
        private: bool = name[0] == "_"
        extra: typing.Mapping[str, typing.Any] = {}
        alias: str = name

        if isinstance(default, FieldInfo):
            field = default

            default_factory = field.default_factory
            alias = field.alias or name
            private = field.private if field.private is not None else private
            extra = field.extra
            validators.extend(field.validators)

            default = field.default

        # not done by default on newer version of python
        if default is None:
            try:
                annotation = typing.Optional[annotation]  # type: ignore
            except Exception:
                pass

        validator = parser.get_validator(annotation, model=model)
        validators.append(validator)

        return cls(
            default,
            default_factory=default_factory,
            alias=alias,
            private=private,
            validators=validators,
            **extra,
        )

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

    __slots__ = ("default", "alias")

    default: object
    alias: str

    def __init__(self, default: object = ..., *, alias: str = "") -> None:
        """Initialize an ExtraInfo."""
        self.default = default
        self.alias = alias


class NamedProperty(property):
    """Property with a public name."""

    alias: str
    exclude: bool

    def __init__(
        self,
        fget: tutils.AnyCallable,
        *,
        alias: typing.Optional[str] = None,
        exclude: typing.Optional[bool] = None,
    ) -> None:
        """Initialize a NamedProperty."""
        super().__init__(fget)
        self.alias = alias or fget.__name__

        if exclude is None:
            exclude = fget.__name__[0] == "_"

        self.exclude = exclude


def Field(
    default: object = ...,
    *,
    default_factory: typing.Optional[typing.Callable[[], object]] = None,
    alias: typing.Optional[str] = None,
    private: typing.Optional[bool] = None,
    validator: tutils.MaybeSequence[tutils.AnyCallable] = (),
    validators: tutils.MaybeSequence[tutils.AnyCallable] = (),
    **extra: typing.Any,
) -> typing.Any:
    """Create a new FieldInfo."""
    return FieldInfo(
        default=default,
        default_factory=default_factory,
        alias=alias,
        private=private,
        validators=utility.flatten_sequences(validator, validators),
        **extra,
    )


def Extra(default: object = ..., alias: str = "") -> typing.Any:
    """Create a new ExtraInfo."""
    return ExtraInfo(default, alias=alias)


def Aliased(
    alias: str,
    *,
    default: object = ...,
    default_factory: typing.Optional[typing.Callable[[], object]] = None,
    private: typing.Optional[bool] = None,
    validator: tutils.MaybeSequence[tutils.AnyCallable] = (),
    validators: tutils.MaybeSequence[tutils.AnyCallable] = (),
    **extra: typing.Any,
) -> typing.Any:
    """Create a new FieldInfo with an alias as the first argument."""
    return FieldInfo(
        default=default,
        default_factory=default_factory,
        alias=alias,
        private=private,
        validators=utility.flatten_sequences(validator, validators),
        **extra,
    )


def named_property(
    alias: typing.Optional[str] = None,
    *,
    exclude: typing.Optional[bool] = None,
) -> typing.Type[NamedProperty]:
    """Create a named property."""

    def wrapper(func: tutils.AnyCallable) -> NamedProperty:
        return NamedProperty(func, alias=alias, exclude=exclude)

    return typing.cast("typing.Type[NamedProperty]", wrapper)
