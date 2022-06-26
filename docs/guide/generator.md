# Code Generation

Models can be generated for you using the CLI.

```
$ curl "https://api.trace.moe/search?url=https://images.plurk.com/32B15UXxymfSMwKGTObY5e.jpg&anilistInfo" | python -m apimodel


import typing

import apimodel

class ResultAnilistTitle(apimodel.APIModel):
    native: str
    romaji: str
    english: typing.Optional[str] = None


class ResultAnilist(apimodel.APIModel):
    id: int
    id_mal: int = apimodel.Field(name="idMal")
    title: ResultAnilistTitle
    synonyms: typing.Sequence[str]
    is_adult: bool = apimodel.Field(name="isAdult")


class Result(apimodel.APIModel):
    anilist: ResultAnilist
    filename: str
    episode: int
    from: float
    to: float
    similarity: float
    video: str
    image: str


class Root(apimodel.APIModel):
    frame_count: int = apimodel.Field(name="frameCount")
    error: str
    result: typing.Sequence[Result]
```

Now all that's left is to rename the generated models.
