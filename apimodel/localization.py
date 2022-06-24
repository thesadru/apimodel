"""Localization support for the API."""
from __future__ import annotations

import collections
import typing

from . import apimodel, fields, tutils

if typing.TYPE_CHECKING:
    import typing_extensions

__all__ = ["LocalizedAPIModel"]


class LocalizedFieldInfo(fields.ModelFieldInfo):
    """Complete information about a localized field."""

    __slots__ = ("i18n", "localizator")

    i18n: typing.Optional[typing.Union[str, typing.Mapping[str, str]]]
    """Localized field names."""

    localizator: typing.Optional[typing.Callable[[typing.Any, str], typing.Optional[object]]]
    """Getter for localized values of the field."""

    def __init__(
        self,
        default: object = ...,
        *,
        name: typing.Optional[str] = None,
        private: typing.Optional[bool] = False,
        validators: tutils.MaybeSequence[tutils.AnyCallable] = ...,
        i18n: typing.Optional[typing.Union[str, typing.Mapping[str, str]]] = None,
        localizator: typing.Optional[typing.Callable[[typing.Any, str], typing.Optional[object]]] = None,
        **extra: typing.Any,
    ) -> None:
        self.i18n = i18n
        self.localizator = localizator

        super().__init__(
            default,
            name=name,
            private=private,
            validators=validators,
            **extra,
        )

    def get_localized_name(
        self,
        provider: typing.Mapping[str, typing.Mapping[str, str]],
        locale: str,
    ) -> str:
        """Get the localized name of the field."""
        i18n = self.i18n or self.name

        if isinstance(i18n, str):
            return provider[locale].get(i18n, self.name)

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
    """Internationalization mapping of `{locale: {key: "localized string"}}`."""

    def __new__(
        cls,
        name: str,
        bases: typing.Tuple[type],
        namespace: typing.Dict[str, object],
        *,
        field_cls: typing.Optional[typing.Type[LocalizedFieldInfo]] = None,
        slots: typing.Optional[bool] = None,
        **options: object,
    ) -> typing_extensions.Self:
        self = super().__new__(cls, name, bases, namespace, field_cls=field_cls or LocalizedFieldInfo, **options)
        self = typing.cast("typing_extensions.Self", self)

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
        alias: typing.Optional[bool] = None,
        locale: typing.Optional[str] = None,
        **options: object,
    ) -> tutils.JSONMapping:
        """Create a mapping from the model instance."""
        obj: tutils.JSONMapping = {}

        locale = locale or self.locale

        if locale is None and alias is None:
            alias = True

        for attr_name, field in self.__class__.__fields__.items():
            if field.private and not private:
                continue

            if alias is not None:
                field_name = field.name if alias else attr_name
            elif locale is not None:
                field_name = field.get_localized_name(self.__class__.i18n, locale)
            else:
                field_name = attr_name

            value = apimodel._serialize_attr(getattr(self, attr_name), private=private, alias=alias, locale=locale)

            if locale is not None:
                value = field.get_localized_value(value, self.__class__.i18n, locale)

            obj[field_name] = value

        return obj
