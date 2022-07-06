# APIModel

[![Downloads](https://pepy.tech/badge/apimodels)](https://pepy.tech/project/apimodels)
[![PyPI package](https://img.shields.io/pypi/v/apimodels)](https://pypi.org/project/apimodels/)
[![Last Commit](https://img.shields.io/github/last-commit/thesadru/apimodel)](https://github.com/thesadru/apimodel/commits/master)
[![Coverage](https://img.shields.io/codeclimate/coverage/thesadru/apimodel)](https://codeclimate.com/github/thesadru/apimodel)
[![Documentation](https://readthedocs.org/projects/apimodel/badge)](https://apimodel.readthedocs.io/en/latest)

Advanced models for non-standard modern JSON APIs.

---

Documentation: <https://apimodel.readthedocs.io/en/latest/>

Source Code: <https://github.com/thesadru/apimodel>

---

Advanced models for non-standard modern JSON APIs. Supports extensive conversion and validation with several tools to help speed up development.
Works with both synchronous and asynchronous models seamlessly.
Fully tested and type-hinted.

## Key Features

- Seamless data parsing through annotations.
- Supports extensive conversion and validation.
- Automatic code generation from json to speed up development.
- Inspired by pydantic to ensure familiarity.
- Localization support.
- Fully tested and type-hinted.
- No requirements.

## Example

You can see more examples in the docs.

```py
import typing

import datetime

import apimodel

class User(apimodel.APIModel):
    id: int
    username: str
    profile: str

    # UNIX or ISO parsing
    created_at: datetime.datetime

    @apimodel.validator()
    def _complete_profile_url(self, profile: str) -> str:
        """Take the raw profile ID and turn it into a full url"""
        return f"https://example.com/assets/profile/{profile}.png"

# inheritance
class Attendee(User):
    status: typing.Literal["attending", "interested", "absent"] | None = None

    @apimodel.root_validator()
    def _parse_status(self, values: dict[str, typing.Any]) -> dict[str, typing.Any]:
        """Take the entire JSON and update it accordingly"""
        # made for non-standard APIs
        if "attending" in values:
            values["status"] = "attending" if values["attending"] else "absent"
        elif "interested" in values:
            values["status"] = "interested" if values["interested"] else "absent"

        # excess values get thrown away
        return values

class Event(apimodel.APIModel):
    # allow easily renaming fields
    time: datetime.datetime = apimodel.Field(alias="happening_at")
    # clean nested models
    attendees: list[User]
```
