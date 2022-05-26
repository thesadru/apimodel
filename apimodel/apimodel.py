"""APIModel class with all the validation."""
from __future__ import annotations

import typing

from . import fields, tutils, utility, validation

ValidatorT = typing.TypeVar("ValidatorT", bound=validation.BaseValidator)
APIModelT = typing.TypeVar("APIModelT", bound="APIModel")


def _get_ordered(validators: typing.Sequence[ValidatorT], order: validation.Order) -> typing.Sequence[ValidatorT]:
    return [validator for validator in validators if order <= validator.order < (order + 10)]


class APIModelMeta(type):
    """API model metaclass.

    Stores fields and validators generated for every model.
    """

    __fields__: typing.Dict[str, fields.ModelFieldInfo]
    __extras__: typing.Dict[str, fields.ExtraInfo]
    __root_validators__: typing.Sequence[validation.RootValidator]

    def __new__(cls, name: str, bases: typing.Tuple[type], namespace: typing.Dict[str, typing.Any]) -> APIModelMeta:
        """Create a new model class.

        Collects all fields and validators.
        """
        self = super().__new__(cls, name, bases, namespace)
        self.__fields__ = {}
        self.__extras__ = {}
        self.__root_validators__ = []

        for name, annotation in typing.get_type_hints(self).items():
            obj = getattr(self, name, ...)
            if isinstance(obj, fields.ExtraInfo):
                continue  # resolved later

            self.__fields__[name] = fields.ModelFieldInfo.from_annotation(name, annotation, obj)

        for name in dir(self):
            obj = getattr(self, name, ...)
            if isinstance(obj, validation.RootValidator):
                self.__root_validators__.append(obj)
            elif isinstance(obj, validation.Validator):
                for field_name in obj._fields:
                    self.__fields__[field_name].add_validators(obj)
            elif isinstance(obj, fields.ExtraInfo):
                obj.name = obj.name or name
                self.__extras__[name] = obj

        self.__root_validators__.sort(key=lambda v: v.order)

        return self

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.__fields__.items())
        return f"{self.__name__}({args})"

    @property
    def isasync(self) -> bool:
        """Whether the model is async."""
        return (
            # field validators
            any(validator.isasync for field in self.__fields__.values() for validator in field.validators)
            # root validators
            or any(validator.isasync for validator in self.__root_validators__)
        )

    def _validate_universal(
        self,
        obj: tutils.JSONMapping,
        *,
        instance: typing.Optional[APIModel] = None,
    ) -> typing.Generator[tutils.MaybeAwaitable[tutils.JSONMapping], tutils.JSONMapping, tutils.JSONMapping]:
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

    def validate_model_sync(
        self,
        obj: tutils.JSONMapping,
        *,
        instance: typing.Optional[APIModel] = None,
    ) -> tutils.JSONMapping:
        """Validate a mapping synchronously.

        Returns the validated mapping.
        If an instance is not passed in, a dummy instance will be created.
        """
        generator = self._validate_universal(obj, instance=instance)
        value = generator.__next__()

        while True:
            try:
                if isinstance(value, typing.Awaitable):
                    raise TypeError("Received awaitable in sync mode.")

                value = generator.send(value)
            except StopIteration as e:
                return e.value

    async def validate_model(
        self,
        obj: tutils.JSONMapping,
        *,
        instance: typing.Optional[APIModel] = None,
    ) -> tutils.JSONMapping:
        """Validate a mapping asynchronously.

        Returns the validated mapping.
        If an instance is not passed in, a dummy instance will be created.
        """
        generator = self._validate_universal(obj, instance=instance)
        value = generator.__next__()

        while True:
            try:
                if isinstance(value, typing.Awaitable):
                    value = await value

                value = generator.send(value)
            except StopIteration as e:
                return e.value

    async def from_mapping(self, obj: tutils.JSONMapping) -> APIModel:
        """Create a model from a mapping."""
        instance = typing.cast("APIModel", object.__new__(self))  # type: ignore
        await self.validate_model(obj, instance=instance)
        return instance


class APIModel(utility.Representation, metaclass=APIModelMeta):
    """Base APIModel class."""

    def __new__(
        cls: typing.Type[APIModelT],
        obj: typing.Optional[typing.Any] = None,
        **kwargs: typing.Any,
    ) -> APIModelT:
        """Create a new model instance.

        All async models should be created using the async factory method.
        """
        return cls.sync_create(obj, **kwargs)

    @classmethod
    def sync_create(
        cls: typing.Type[APIModelT],
        obj: typing.Optional[typing.Any] = None,
        **kwargs: typing.Any,
    ) -> APIModelT:
        """Create a new model instance synchronously."""
        if cls.isasync:
            raise TypeError("Must use from_mapping with an async APIModel.")
        if obj is None and not kwargs:
            raise TypeError(f"{cls.__name__} expected at least 1 argument.")

        if isinstance(obj, cls):
            return obj
        if isinstance(obj, APIModel):
            obj = obj.__dict__  # TODO
        if obj is None:
            obj = {}

        if not isinstance(obj, typing.Mapping):
            raise TypeError(f"Unparsable object: {obj}")

        obj = {**obj, **kwargs}

        self = super().__new__(cls)
        self.update_model_sync(obj)
        return self

    @classmethod
    async def create(
        cls: typing.Type[APIModelT],
        obj: typing.Optional[typing.Any] = None,
        **kwargs: typing.Any,
    ) -> APIModelT:
        """Create a new model instance asynchronously."""
        if obj is None and not kwargs:
            raise TypeError(f"{cls.__name__} expected at least 1 argument.")

        if isinstance(obj, cls):
            return obj
        if isinstance(obj, APIModel):
            obj = obj.__dict__  # TODO
        if obj is None:
            obj = {}

        if not isinstance(obj, typing.Mapping):
            raise TypeError(f"Unparsable object: {obj}")

        obj = {**obj, **kwargs}

        self = super().__new__(cls)
        await self.update_model(obj)
        return self

    def update_model_sync(self, obj: tutils.JSONMapping) -> tutils.JSONMapping:
        """Update a model instance synchronously."""
        return self.__class__.validate_model_sync(obj, instance=self)

    async def update_model(self, obj: tutils.JSONMapping) -> tutils.JSONMapping:
        """Update a model instance asynchronously."""
        return await self.__class__.validate_model(obj, instance=self)

    def as_dict(self, *, private: bool = False, alias: bool = True) -> tutils.JSONMapping:
        """Create a mapping from the model instance."""
        obj: tutils.JSONMapping = {}

        for attr_name, field in self.__class__.__fields__.items():
            if field.private and not private:
                continue

            field_name = field.name if alias else attr_name
            obj[field_name] = self.__dict__[attr_name]

        return obj

    def get_extras(self, alias: bool = True) -> typing.Mapping[str, typing.Any]:
        """Get extra fields which are normally not part of the model."""
        obj: typing.Mapping[str, typing.Any] = {}

        for attr_name, extra in self.__class__.__extras__.items():
            field_name = extra.name if alias else attr_name
            obj[field_name] = self.__dict__[attr_name]

        return obj

    def __repr_args__(self) -> typing.Mapping[str, typing.Any]:
        return self.as_dict(private=True, alias=False)
