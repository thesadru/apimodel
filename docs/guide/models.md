# Models

APIModel is inspired by [pydantic](https://github.com/samuelcolvin/pydantic) and based on annotations. If you have used pydantic before this library should be seem familiar to you.

Models are defined by inheriting from [apimodel.APIModel](apimodel.apimodel.APIModel).

## Basic usage

We define a model with two fields. An integer `id` and an optional string `name`.

```py
import apimodel

class User(apimodel.APIModel):
    id: int
    name: str = "Anonymous"

user = User(id="123")
print(user)
# User(id=123, name='Anonymous')
```

`user.id` has been casted to an integer and `user.name` has the default value.

```py
print(user.as_dict())
# {'id': 123, 'name': 'Anonymous'}
```

## Model Nesting

Models can be nested

```py
class Item(apimodel.APIModel):
    name: str

class Storage(apimodel.APIModel):
    max_size: int = 256
    items: list[Item]

class User(apimodel.APIModel):
    id: int
    storage: Storage


user = User(id="123", storage={"items": [{"name": "foo"}, {"name": "bar"}]})
print(user)
# User(id=123, storage=Storage(items=[Item(name='foo'), Item(name='bar')], max_size=256))

print(user.storage.items[0].name)
# foo
```

```{warning}
`list[object]` is available only in python 3.9+

Please use [typing.Sequence](typing.Sequence) on lower version.
```

## Fields

Metadata can be added to fields through [apimodel.fields.FieldInfo](apimodel.fields.FieldInfo) at runtime.

The first positional argument is always the default value. [`...`](Ellipsis) denotes a required value.

See [apimodel.FieldInfo](apimodel.fields.FieldInfo) for details.

```py
import datetime
import apimodel

class Item(apimodel.APIModel):
    id: int = apimodel.Field(..., private=True)
    created_at: datetime.datetime = apimodel.Field(..., name="createdAt")
    available: bool = apimodel.Field(False)


item = Item({"id": "42", "name": "foo", "createdAt": 1577836800})
print(item.as_dict())
# {'created_at': datetime.datetime(2020, 1, 1, 0, 0, tzinfo=datetime.timezone.utc), 'available': False}
print(item.id)
# 42
```

## Extras

Some values may require to be shared across all nested models. For example your API client. This can be done with inheritance and [apimodel.Extra](apimodel.fields.Extra).

Extra values do not appear in [model.as_dict()](apimodel.apimodel.APIModel.as_dict)

```py
class Client:
    def __init__(self, token: str) -> None:
        self.token = token

    def fetch_user(self, id: int) -> User:
        data = self._request_endpoint("GET", f"/users/{id}")
        return User(data, client=self)

    def edit_user(self, user_id: int, **kwargs: object) -> None:
        ...

    def buy_item(self, item_id: int) -> None:
        ...

    ...

class BaseModel(apimodel.APIModel):
    # underscore gets stripped at runtime
    _client: Client = apimodel.Extra()

class Item(BaseModel):
    id: int
    name: str

    def buy(self) -> None:
        self.client.buy_item(self.id)

class User(BaseModel):
    id: int
    name: str
    items: list[Item]

    def edit(self, **kwargs: object) -> None:
        self.client.edit_user(self.id, **kwargs)

client = Client("token")

user = client.fetch_user(42)
print(user)
# User(id=1, name='John', items=[Item(id=42, name='foo'), Item(id=43, name='bar')])

user.edit(name="John Doe")
user.items[1].buy()
```

## Debugging

APIModel can be used with [python-devtools](https://python-devtools.helpmanual.io/) developed by the author of [pydantic](https://github.com/samuelcolvin/pydantic).
