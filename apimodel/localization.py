"""Localization support for the API."""
from __future__ import annotations

import collections
import typing

from . import apimodel, fields, tutils

__all__ = ["LocalizedAPIModel", "LocalizedAPIModelMeta", "LocalizedFieldInfo"]


class LocalizedFieldInfo(fields.ModelFieldInfo):
    """Complete information about a localized field."""

    __slots__ = ("i18n", "localizator")

    i18n: typing.Optional[typing.Union[str, typing.Mapping[str, str]]]
    """Localized field names."""

    localizator: typing.Optional[typing.Callable[[typing.Any, str], typing.Optional[object]]]
    """Getter for localized values of the field. Called in `LocalizedAPIModel.as_dict`."""

    def __init__(
        self,
        default: object = ...,
        *,
        alias: typing.Optional[str] = None,
        private: typing.Optional[bool] = False,
        validators: tutils.MaybeSequence[tutils.AnyCallable] = ...,
        i18n: typing.Optional[typing.Union[str, typing.Mapping[str, str]]] = None,
        localizator: typing.Optional[typing.Callable[[typing.Any, str], typing.Optional[object]]] = None,
        **extra: typing.Any,
    ) -> None:
        """Initialize a LocalizedFieldInfo.

        Extra arguments may be repurposed for subclass attributes.
        """
        self.i18n = i18n
        self.localizator = localizator

        super().__init__(
            default,
            alias=alias,
            private=private,
            validators=validators,
            **extra,
        )

    def get_localized_name(
        self,
        provider: typing.Mapping[str, typing.Mapping[str, str]],
        locale: str,
        name: typing.Optional[str] = None,
    ) -> str:
        """Get the localized name of the field."""
        i18n = self.i18n or name or self.alias

        if isinstance(i18n, str):
            return provider[locale].get(i18n, name or self.alias)

        return i18n[locale]

    def get_localized_value(
        self,
        value: object,
        provider: typing.Mapping[str, typing.Mapping[str, str]],
        locale: str,
    ) -> object:
        """Get the localized value of the field.."""
        if self.localizator is not None:
            return self.localizator(value, locale) or value

        if isinstance(value, str):
            return provider[locale].get(value, value)

        return value


class LocalizedAPIModelMeta(apimodel.APIModelMeta):
    """Localized API model metaclass."""

    __fields__: typing.Mapping[str, LocalizedFieldInfo]

    i18n: typing.ClassVar[typing.Dict[str, typing.Dict[str, str]]] = collections.defaultdict(dict)
    """Internationalization mapping of ``{locale: {key: "localized string"}}``."""

    def __new__(
        cls,
        name: str,
        bases: typing.Tuple[type],
        namespace: typing.Dict[str, object],
        *,
        field_cls: typing.Optional[typing.Type[LocalizedFieldInfo]] = None,
        **options: object,
    ) -> tutils.Self:
        """Create a new model class.

        Collects all fields and validators.
        """
        self = super().__new__(cls, name, bases, namespace, field_cls=field_cls or LocalizedFieldInfo, **options)
        self = typing.cast("tutils.Self", self)

        return self

    def set_i18n(self, locale: str, key: str, value: str) -> None:
        """Set a new i18n entry."""
        self.i18n[locale][key] = value


class LocalizedAPIModel(apimodel.APIModel, metaclass=LocalizedAPIModelMeta):
    """Localized API model."""

    __slots__ = ()

    locale: typing.Optional[str] = fields.Extra(None)

    def as_dict(
        self,
        *,
        private: bool = False,
        properties: bool = True,
        alias: typing.Optional[bool] = None,
        locale: typing.Optional[str] = None,
        **options: object,
    ) -> typing.Mapping[str, object]:
        """Create a mapping from the model instance.

        Args:
            private: Include private attributes (prefixed with an underscore `_`).
            properties: Include methods decorated with `@property`.
            alias: Rename fields to their declared name if they cannot be localized.
                If `False`, do not rename any field even if it can be localized.
            locale: Locale to use for localization. By default the locale of the model instance is used.
        """
        obj: typing.Mapping[str, object] = {}

        locale = locale or self.locale

        for attr_name, field in self.__class__.__fields__.items():
            if field.private and not private:
                continue

            field_name = field.alias if alias else attr_name

            if locale is not None and alias is not False:
                field_name = field.get_localized_name(self.__class__.i18n, locale, name=field_name)

            value = apimodel._serialize_attr(getattr(self, attr_name), private=private, alias=alias, locale=locale)

            if locale is not None:
                value = field.get_localized_value(value, self.__class__.i18n, locale)

            obj[field_name] = value

        if properties:
            obj.update({name: getattr(self, attr_name) for attr_name, name in self.__class__.__properties__.items()})

        return obj
