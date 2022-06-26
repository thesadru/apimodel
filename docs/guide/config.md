# Configuration

APIModel does not provide traditional configuration in the form of `Config` classes. Instead, it expects users to overwrite individual methods to customize the behavior of the model.

```{note}
Before attempting to patch the internals try to see if a [validator](validators.md) can do the job.
```

## Model Inspection

Fields are available through [Model.**fields**](apimodel.apimodel.APIModelMeta.__fields__). That means you can do `Model.__fields__["a"]` but not `Model.a` or `Model().__fields__["a"]`.
This and other similar special attributes are unavailable on the instances `Model()`.

See [apimodel.APIModelMeta](apimodel.apimodel.APIModelMeta) for details.

## Custom Fields

Custom [apimodel.ModelFieldInfo](apimodel.fields.ModelFieldInfo) subclasses can be set as fields through `field_cls`.

```py
class CustomFieldInfo(apimodel.fields.ModelFieldInfo):
    def __init__(self, default: object = ..., *, foo: int = 0, **kwargs: object):
        super().__init__(default, **kwargs)
        self.foo = foo


        validator = apimodel.Validator(lambda value: logger.debug("%s: %s", self.name, value) or x)
        self.add_validators(validator)


class CustomModel(apimodel.APIModel, field_cls=CustomFieldInfo):
    id: int = apimodel.Field(foo=1)

print(CustomModel.__fields__["id"].foo)
# 1

instance = CustomModel(id=42)
# 2020-01-01T00:00:00+00:00 DEBUG id: 42
```

##
