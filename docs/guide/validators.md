# Validators

Many non-standard fields won't be parseable with just an annotation. Define a validator to parse them properly.

The order of validators is determined by [apimodel.Order](apimodel.validation.Order)

```py
class User(apimodel.APIModel):
    username: str
    bio: str
    profile_image: str

    @apimodel.validator("username", "bio")
    def _strip_string(self, string: str) -> None:
        return string.strip()

    @apimodel.validator("profile_image")
    def _validate_image_url(self, image: str) -> None:
        if "http"  in url:
            return image

        return f"https://example.com/assets/profile/{image}.png"
```

## Root Validators

Root Validators operate upon the entire field at once.

```py
class Model(apimodel.APIModel):
    foo: int
    bar: int
    baz: int

    @apimodel.root_validator(order=apimodel.Order.INITIAL_ROOT)
    def _remove_nesting(self, values: dict[str, typing.Any]) -> dict[str, typing.Any]:
        values["bar"] = values["nested"]["bar"]
        values["baz"] = values["nested"]["baz"]

        return values
```

## AsyncIO

Any validator can be asynchronous. In that case the model must be created asynchronously through [await Model.create(...)](apimodel.apimodel.APIModel.create).

```py
class User(apimodel.APIModel):
    username: str
    profile: str

    @apimodel.root_validator()
    async def _fetch_image(self, values: dict[str, typing.Any]) -> dict[str, typing.Any]:
        response = await aiohttp.request("GET", f"https://example.com/api/users/{values['username']}/profile")
        data = await response.json()
        values["profile"] = data["profile"]["small"]["url"]

        return values

await User.create(username="johndoe")
```
