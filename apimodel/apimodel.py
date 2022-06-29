"""APIModel class with all the validation."""
from __future__ import annotations

import typing

from . import errors, fields, tutils, utility, validation

if typing.TYPE_CHECKING:
    import typing_extensions

__all__ = ["APIModel", "APIModelMeta", "create_model"]

ValidatorT = typing.TypeVar("ValidatorT", bound=validation.BaseValidator)
APIModelT = typing.TypeVar("APIModelT", bound="APIModel")


def _get_ordered(validators: typing.Sequence[ValidatorT], order: validation.Order) -> typing.Sequence[ValidatorT]:
    """Get validators that fall into the selected order category."""
    return [validator for validator in validators if order <= validator.order < (order + 10)]


def _serialize_attr(attr: object, **kwargs: object) -> object:
    """Serialize an attribute."""
    if isinstance(attr, APIModel):
        return attr.as_dict(**kwargs)
    if isinstance(attr, typing.Collection) and not isinstance(attr, str):
        return [_serialize_attr(x, **kwargs) for x in typing.cast("typing.Collection[object]", attr)]

    return attr


def _to_mapping(obj: object, **kwargs: object) -> typing.Mapping[str, object]:
    """Turn an arbitrary object into a mapping for APIModel."""
    if isinstance(obj, APIModel):
        obj = obj.as_dict()

    if obj is None:
        obj = {}

    if not isinstance(obj, typing.Mapping):
        raise TypeError(f"Unparsable object: {obj}")

    return {**obj, **kwargs}


class APIModelMeta(type):
    """API model metaclass.

    Stores fields and validators generated for every model.
    """

    __slots__: typing.Sequence[str]

    __fields__: typing.Mapping[str, fields.ModelFieldInfo]
    """Fields with their validators."""

    __extras__: typing.Mapping[str, fields.ExtraInfo]
    """Extra values."""

    __root_validators__: typing.Sequence[validation.RootValidator]
    """Root validators."""

    def __new__(
        cls,
        name: str,
        bases: typing.Tuple[type],
        namespace: typing.Dict[str, object],
        *,
        field_cls: typing.Optional[typing.Type[fields.ModelFieldInfo]] = None,
        slots: typing.Optional[bool] = None,
        **options: object,
    ) -> typing_extensions.Self:
        """Create a new model class.

        Collects all fields and validators.
        """
        self = super().__new__(cls, name, bases, namespace)
        self.__fields__ = {}
        self.__extras__ = {}
        self.__root_validators__ = []

        if field_cls is None:
            possible: typing.Collection[typing.Type[fields.ModelFieldInfo]]
            possible = set(type(field) for base in bases for field in getattr(base, "__fields__", {}).values())
            field_cls = next(iter(possible)) if len(possible) == 1 else fields.ModelFieldInfo

        slots = hasattr(bases[0], "__slots__") if slots is None else slots

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

        if slots and "__slots__" not in namespace:
            previous_slots = set(slot for base in bases for slot in utility.get_slots(base))
            all_slots = set((*self.__fields__.keys(), *self.__extras__.keys()))
            self.__slots__ = tuple(all_slots - previous_slots)

        return self

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.__fields__.items())
        return f"{self.__class__.__name__}({self.__name__!r}, {args})"

    def __devtools_pretty(self, fmt: typing.Callable[[object], str], **kwargs: object) -> typing.Iterator[object]:
        """Devtools pretty formatting."""
        yield from utility.devtools_pretty(
            fmt,
            self.__name__,
            self.__root_validators__,
            __name__=self.__class__.__name__,
            **self.__extras__,
            **self.__fields__,
        )

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
    def _validate_universal(  # noqa # C901: too complex
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
            instance = APIModel._empty(freeform=True)

        self = typing.cast("typing.Type[APIModel]", self)

        # =============================
        # INITIAL ROOT

        with errors.catch_errors(self) as catcher:
            for validator in _get_ordered(self.__root_validators__, order=validation.Order.INITIAL_ROOT):
                with catcher.catch():
                    obj = yield validator(instance, obj)

        obj = dict(obj)

        # =============================
        # ALIAS / EXTRAS
        new_obj: tutils.JSONMapping = {}

        for attr_name, field in self.__fields__.items():
            if field.name not in obj and field.default is not ...:
                obj[field.name] = field.default

            if field.name in obj:
                setattr(instance, attr_name, obj[field.name])
                new_obj[attr_name] = obj[field.name]

        if extras:
            with errors.catch_errors(self) as catcher:
                for attr_name, extra in self.__extras__.items():
                    if extra.name in obj:
                        setattr(instance, attr_name, obj[extra.name])
                    elif extra.default is not ...:
                        setattr(instance, attr_name, extra.default)
                    else:
                        catcher.add_error(TypeError(f"Missing required extra field: {extra.name!r}"), loc=attr_name)

        obj = new_obj

        # =============================
        # ROOT
        with errors.catch_errors(self) as catcher:
            for validator in _get_ordered(self.__root_validators__, order=validation.Order.ROOT):
                with catcher.catch():
                    obj = yield validator(instance, obj)

        # =============================
        # FIELD CHECK
        with errors.catch_errors(self) as catcher:
            for attr_name, field in self.__fields__.items():
                if attr_name not in obj:
                    catcher.add_error(TypeError(f"Missing required field: {field.name!r}"), loc=attr_name)

        obj = dict(obj)

        # =============================
        # VALIDATOR
        orders = (validation.Order.VALIDATOR, validation.Order.ANNOTATION, validation.Order.POST_VALIDATOR)
        for order in orders:
            # order is next to arbitrary, only here because of ANNOTATION
            with errors.catch_errors(self) as catcher:
                for attr_name, field in self.__fields__.items():
                    for validator in _get_ordered(field.validators, order=order):
                        with catcher.catch(loc=attr_name):
                            obj[attr_name] = yield validator(instance, obj[attr_name])
                            setattr(instance, attr_name, obj[attr_name])

        # =============================
        # FINAL ROOT
        with errors.catch_errors(self) as catcher:
            for validator in _get_ordered(self.__root_validators__, order=validation.Order.FINAL_ROOT):
                with catcher.catch():
                    obj = yield validator(instance, obj)

        # =============================
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

    # populated by metaclass
    __slots__ = ()

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

        self = super().__new__(cls)
        self.update_model_sync(_to_mapping(obj, **kwargs))
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

        self = super().__new__(cls)
        await self.update_model(_to_mapping(obj, **kwargs))
        return self

    def update_model_sync(self, obj: tutils.JSONMapping) -> tutils.JSONMapping:
        """Update a model instance synchronously."""
        return self.__class__.validate_sync(obj, instance=self, extras=True)

    async def update_model(self, obj: tutils.JSONMapping) -> tutils.JSONMapping:
        """Update a model instance asynchronously."""
        return await self.__class__.validate(obj, instance=self, extras=True)

    def as_dict(self, *, private: bool = False, alias: bool = False, **options: object) -> tutils.JSONMapping:
        """Create a mapping from the model instance."""
        obj: tutils.JSONMapping = {}

        for attr_name, field in self.__class__.__fields__.items():
            if field.private and not private:
                continue

            field_name = field.name if alias else attr_name
            attr = getattr(self, attr_name)
            obj[field_name] = _serialize_attr(attr, private=private, alias=alias)

        return obj

    def get_extras(self, alias: bool = True) -> typing.Mapping[str, object]:
        """Get extra fields which are normally not part of the model."""
        obj: typing.Mapping[str, object] = {}

        for attr_name, extra in self.__class__.__extras__.items():
            field_name = extra.name if alias else attr_name
            if hasattr(self, attr_name):
                obj[field_name] = getattr(self, attr_name)

        return obj

    def __repr_args__(self) -> typing.Mapping[str, object]:
        return {attr: getattr(self, attr) for attr in self.__class__.__fields__}

    @classmethod
    def __get_validators__(cls) -> typing.Iterator[typing.Callable[..., object]]:
        """Get pydantic validators for compatibility."""
        yield cls.sync_create

    @classmethod
    def __modify_schema__(cls, field_schema: typing.Dict[str, object]) -> None:
        """Create a schema for pydantic."""
        field_schema.update(
            type="object",
            properties={field.name: dict(type="any") for field in cls.__fields__.values() if not field.private},
        )

    @classmethod
    def _empty(cls, freeform: bool = False) -> APIModel:
        """Return an empty base APIModel."""
        if freeform:
            cls = type(cls.__name__, (cls,), {})

        return super().__new__(cls)


def create_model(
    __name__: str,
    __bases__: tutils.MaybeSequence[typing.Type[APIModel]] = APIModel,
    /,
    __fields__: typing.Optional[typing.Mapping[str, fields.ModelFieldInfo]] = None,
    __extras__: typing.Optional[typing.Mapping[str, fields.ExtraInfo]] = None,
    __root_validators__: typing.Optional[typing.Sequence[validation.RootValidator]] = None,
    **attrs: typing.Union[object, fields.FieldInfo, fields.ExtraInfo, typing.Tuple[object, object]],
) -> typing.Type[APIModel]:
    """Dynamically create a model.

    Fields must be in the formats `name=type` | `name=FieldInfo()` | `name=(type, default)`
    """
    namespace: typing.Dict[str, typing.Any] = {}
    annotations = namespace["__annotations__"] = {}
    for name, attr in attrs.items():
        if isinstance(attr, (fields.FieldInfo, fields.ExtraInfo)):
            namespace[name] = attr
            annotations[attr] = attr.tp if isinstance(attr, fields.ModelFieldInfo) else object
        elif isinstance(attr, tuple):
            attr = typing.cast("typing.Tuple[object, object]", attr)
            if len(attr) != 2:
                raise TypeError("Tuple must be (type, default)")

            annotations[name] = attr[0]
            namespace[name] = attr[1]
        else:
            annotations[name] = attr

    model: typing.Type[APIModel] = type(__name__, tuple(utility.flatten_sequences(__bases__)), namespace)  # type: ignore

    if __fields__:
        model.__fields__ = {**model.__fields__, **__fields__}
    if __extras__:
        model.__extras__ = {**model.__extras__, **__extras__}
    if __root_validators__:
        model.__root_validators__ = [*model.__root_validators__, *__root_validators__]

    return model
