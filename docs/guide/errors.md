# Error Handling

`ValidationError` will be raised whenever an error is found during validation. It contains a list of `LocError` which have an attached location of error.

See [apimodel.ValidationError](apimodel.errors.ValidationError) for details.

```py
import apimodel

class Location(apimodel.APIModel):
    lat: float = 0.1
    lng: float = 10.1


class Model(apimodel.APIModel):
    number: float = 0.0
    integers: list[int]
    location: Location


data = dict(
    numer='not a float',
    integers=['1', 2, 'bad'],
    location={'lat': 4.2, 'lng': 'New York'},
)

try:
    Model(**data)
except apimodel.ValidationError as e:
    print(e)
    """
3 validation errors for Model
number
  ValueError: could not convert string to float: 'not a float'
integers -> 2
  ValueError: invalid literal for int() with base 10: 'bad'
location -> lng
  ValueError: could not convert string to float: 'New York'
    """

    print(e.locations)
    """
[
    (
        ('number',),
        ValueError("could not convert string to float: 'not a float'"),
    ),
    (
        ('integers', 2),
        ValueError("invalid literal for int() with base 10: 'bad'"),
    ),
    (
        ('location', 'lng'),
        ValueError("could not convert string to float: 'New York'"),
    )
]
  """
```
