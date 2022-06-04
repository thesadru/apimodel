"""Field descriptors."""
from __future__ import annotations

import typing

from . import parser, tutils, utility, validation

__all__ = ["Extra", "ExtraInfo", "Field", "FieldInfo", "ModelFieldInfo"]

T = typing.TypeVar("T")


class FieldInfo(utility.Representation):
    """Basic information about a field."""

    __slots__ = ("default", "name", "private", "validators")

    default: object
    name: typing.Optional[str]
    private: bool
    validators: typing.List[validation.Validator]

    def __init__(
        self,
        default: object = ...,
        *,
        name: typing.Optional[str] = None,
        private: bool = False,
        validator: tutils.MaybeSequence[tutils.AnyCallable] = (),
    ) -> None:
        self.default = default
        self.name = name
        self.private = private

        if not isinstance(validator, typing.Sequence):
            validator = [validator]

        self.validators = [
            callback if isinstance(callback, validation.Validator) else validation.Validator(callback)
            for callback in validator
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

    @classmethod
    def from_annotation(cls, name: str, annotation: object, default: object = ...) -> ModelFieldInfo:
        """Create a new model field info from an annotation.

        If the default is already a FieldInfo, the data is copied.
        """
        validators: typing.Sequence[validation.Validator] = []
        private = name[0] == "_"

        if isinstance(default, FieldInfo):
            name = default.name or name
            private = default.private
            validators.extend(default.validators)

            default = default.default

        validator = parser.get_validator(annotation)
        validator.tp = annotation
        validators.append(validator)

        return cls(default, name=name, private=private, validator=validators)


class ExtraInfo(utility.Representation):
    """Descriptor for a special extra attribute."""

    __slots__ = ("name",)

    name: str

    def __init__(self, name: str = "") -> None:
        self.name = name


def Field(
    default: object = ...,
    *,
    name: typing.Optional[str],
    private: bool = False,
    validator: tutils.MaybeSequence[tutils.AnyCallable],
) -> typing.Any:
    """Create a new FieldInfo."""
    return FieldInfo(
        default=default,
        name=name,
        private=private,
        validator=validator,
    )


def Extra(name: str = "") -> typing.Any:
    """Create a new ExtraInfo."""
    return ExtraInfo(name=name)
