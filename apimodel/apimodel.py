"""APIModel class with all the validation."""
from __future__ import annotations

import typing

from . import fields, tutils, utility, validation

if typing.TYPE_CHECKING:
    import typing_extensions

__all__ = ["APIModel"]

ValidatorT = typing.TypeVar("ValidatorT", bound=validation.BaseValidator)
APIModelT = typing.TypeVar("APIModelT", bound="APIModel")


def _get_ordered(validators: typing.Sequence[ValidatorT], order: validation.Order) -> typing.Sequence[ValidatorT]:
    return [validator for validator in validators if order <= validator.order < (order + 10)]


def _serialize_attr(attr: object, **kwargs: object) -> object:
    """Serialize an attribute."""
    if isinstance(attr, APIModel):
        return attr.as_dict(**kwargs)
    if isinstance(attr, typing.Collection) and not isinstance(attr, str):
        return [_serialize_attr(x) for x in typing.cast("typing.Collection[object]", attr)]

    return attr


class APIModelMeta(type):
    """API model metaclass.

    Stores fields and validators generated for every model.
    """

    __fields__: typing.Mapping[str, fields.ModelFieldInfo]
    __extras__: typing.Mapping[str, fields.ExtraInfo]
    __root_validators__: typing.Sequence[validation.RootValidator]

    def __new__(
        cls,
        name: str,
        bases: typing.Tuple[type],
        namespace: typing.Dict[str, object],
        *,
        field_cls: typing.Optional[typing.Type[fields.ModelFieldInfo]] = None,
    ) -> typing_extensions.Self:
        """Create a new model class.

        Collects all fields and validators.
        """
        self = super().__new__(cls, name, bases, namespace)
        self.__fields__ = {}
        self.__extras__ = {}
        self.__root_validators__ = []

        field_cls = field_cls or fields.ModelFieldInfo

        for name, annotation in typing.get_type_hints(self).items():
            obj = getattr(self, name, ...)
            if isinstance(obj, fields.ExtraInfo):
                continue  # resolved later

            self.__fields__[name] = field_cls.from_annotation(name, annotation, obj)

        for name in dir(self):
            obj = getattr(self, name, ...)
            if isinstance(obj, validation.RootValidator):
                self.__root_validators__.append(obj)
            elif isinstance(obj, validation.Validator):
                for field_name in obj._fields:
                    self.__fields__[field_name].add_validators(obj)
            elif isinstance(obj, fields.ExtraInfo):
                obj.name = obj.name or name.lstrip("_")
                self.__extras__[name] = obj

        self.__root_validators__.sort(key=lambda v: v.order)

        return self

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.__fields__.items())
        return f"{self.__class__.__name__}({args})"

    def __devtools_pretty(self, fmt: typing.Callable[[object], str], **kwargs: object) -> typing.Iterator[object]:
        """Devtools pretty formatting."""
        yield self.__class__.__name__
        yield "("
        yield 1

        yield from utility.devtools_pretty(
            fmt,
            self.__name__,
            self.__root_validators__,
            **self.__extras__,
            **self.__fields__,
        )

        yield -1
        yield ")"

    if not typing.TYPE_CHECKING:

        def __getattribute__(self, name: str) -> object:
            if name == "__pretty__":
                return self.__devtools_pretty

            return super().__getattribute__(name)

    @property
    def isasync(self) -> bool:
        """Whether the model is async."""
        return (
            # field validators
            any(validator.isasync for field in self.__fields__.values() for validator in field.validators)
            # root validators
            or any(validator.isasync for validator in self.__root_validators__)
        )

    @utility.as_universal
    def _validate_universal(
        self,
        obj: tutils.JSONMapping,
        *,
        instance: typing.Optional[APIModel] = None,
        extras: bool = False,
    ) -> tutils.UniversalAsyncGenerator[tutils.JSONMapping]:
        """Universal validation.

        This method is used by both sync and async validation.
        Yields the return values of validators which may potentially be async and expects a resolved value to be sent back.

        If an instance is not passed in, a dummy instance will be created.
        """
        if instance is None:
            instance = typing.cast("APIModel", object.__new__(self))  # type: ignore

        # INITIAL ROOT
        for validator in _get_ordered(self.__root_validators__, order=validation.Order.INITIAL_ROOT):
            obj = yield validator(instance, obj)

        obj = dict(obj)

        # ALIAS
        new_obj: tutils.JSONMapping = {}

        for attr_name, field in self.__fields__.items():
            if field.name not in obj and field.default is not ...:
                obj[field.name] = field.default

            if field.name in obj:
                setattr(instance, attr_name, obj[field.name])
                new_obj[attr_name] = obj[field.name]

        if extras:
            for attr_name, extra in self.__extras__.items():
                if extra.name not in obj:
                    raise TypeError(f"Missing required extra attribute {extra.name}.")

                setattr(instance, attr_name, obj[extra.name])

        obj = new_obj

        # ROOT
        for validator in _get_ordered(self.__root_validators__, order=validation.Order.ROOT):
            obj = yield validator(instance, obj)

        obj = dict(obj)

        # VALIDATOR
        orders = (validation.Order.VALIDATOR, validation.Order.ANNOTATION, validation.Order.POST_VALIDATOR)
        for attr_name, field in self.__fields__.items():
            if attr_name not in obj:
                raise TypeError("Missing field: " + attr_name)

            for order in orders:
                for validator in _get_ordered(field.validators, order=order):
                    obj[attr_name] = yield validator(instance, obj[attr_name])
                    setattr(instance, attr_name, obj[attr_name])

        # FINAL ROOT
        for validator in _get_ordered(self.__root_validators__, order=validation.Order.FINAL_ROOT):
            obj = yield validator(instance, obj)

        return obj

    def validate_sync(
        self,
        obj: tutils.JSONMapping,
        *,
        instance: typing.Optional[APIModel] = None,
        extras: bool = False,
    ) -> tutils.JSONMapping:
        """Validate a mapping synchronously.

        Returns the validated mapping.
        If an instance is not passed in, a dummy instance will be created.
        """
        return self._validate_universal.synchronous(self, obj, instance=instance, extras=extras)

    async def validate(
        self,
        obj: tutils.JSONMapping,
        *,
        instance: typing.Optional[APIModel] = None,
        extras: bool = False,
    ) -> tutils.JSONMapping:
        """Validate a mapping asynchronously.

        Returns the validated mapping.
        If an instance is not passed in, a dummy instance will be created.
        """
        return await self._validate_universal.asynchronous(self, obj, instance=instance, extras=extras)


class APIModel(utility.Representation, metaclass=APIModelMeta):
    """Base APIModel class."""

    def __new__(
        cls: typing.Type[APIModelT],
        obj: typing.Optional[object] = None,
        **kwargs: object,
    ) -> APIModelT:
        """Create a new model instance.

        All async models should be created using the async factory method.
        """
        return cls.sync_create(obj, **kwargs)

    @classmethod
    def _check_init_args(
        cls,
        obj: typing.Optional[object] = None,
        **kwargs: object,
    ) -> tutils.JSONMapping:
        """Check the arguments passed to the constructor.

        Returns a mapping appropriate for passing to the validator.
        """
        if isinstance(obj, APIModel):
            obj = obj.as_dict()
        if obj is None:
            obj = {}

        if not isinstance(obj, typing.Mapping):
            raise TypeError(f"Unparsable object: {obj}")

        return {**obj, **kwargs}

    @classmethod
    def sync_create(
        cls: typing.Type[APIModelT],
        obj: typing.Optional[object] = None,
        **kwargs: object,
    ) -> APIModelT:
        """Create a new model instance synchronously."""
        if cls.isasync:
            raise TypeError("Must use the create method with an async APIModel.")

        if isinstance(obj, cls):
            return obj

        obj = cls._check_init_args(obj, **kwargs)

        self = super().__new__(cls)
        self.update_model_sync(obj)
        return self

    @classmethod
    async def create(
        cls: typing.Type[APIModelT],
        obj: typing.Optional[object] = None,
        **kwargs: object,
    ) -> APIModelT:
        """Create a new model instance asynchronously."""
        if isinstance(obj, cls):
            return obj

        obj = cls._check_init_args(obj, **kwargs)

        self = super().__new__(cls)
        await self.update_model(obj)
        return self

    def update_model_sync(self, obj: tutils.JSONMapping) -> tutils.JSONMapping:
        """Update a model instance synchronously."""
        return self.__class__.validate_sync(obj, instance=self, extras=True)

    async def update_model(self, obj: tutils.JSONMapping) -> tutils.JSONMapping:
        """Update a model instance asynchronously."""
        return await self.__class__.validate(obj, instance=self, extras=True)

    def as_dict(self, *, private: bool = False, alias: bool = True) -> tutils.JSONMapping:
        """Create a mapping from the model instance."""
        obj: tutils.JSONMapping = {}

        for attr_name, field in self.__class__.__fields__.items():
            if field.private and not private:
                continue

            field_name = field.name if alias else attr_name
            attr = self.__dict__[attr_name]
            obj[field_name] = _serialize_attr(attr, private=private, alias=alias)

        return obj

    def get_extras(self, alias: bool = True) -> typing.Mapping[str, object]:
        """Get extra fields which are normally not part of the model."""
        obj: typing.Mapping[str, object] = {}

        for attr_name, extra in self.__class__.__extras__.items():
            field_name = extra.name if alias else attr_name
            if attr_name in self.__dict__:
                obj[field_name] = self.__dict__[attr_name]

        return obj

    def __repr_args__(self) -> typing.Mapping[str, object]:
        return self.__dict__

    @classmethod
    def __get_validators__(cls) -> typing.Iterator[typing.Callable[..., object]]:
        """Get pydantic validators for compatibility."""
        yield cls.sync_create

    @classmethod
    def __modify_schema__(cls, field_schema: typing.Dict[str, object], *, experimental: bool = False) -> None:
        """Create a schema for pydantic."""
        field_schema.update(
            type="object",
            properties={field.name: dict(type="any") for field in cls.__fields__.values() if not field.private},
        )
