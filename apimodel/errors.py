"""Pretty errors."""
from __future__ import annotations

import typing

from . import apimodel, utility

__all__ = ["ValidationError"]


Loc = typing.Tuple[typing.Union[int, str], ...]
ErrorList = typing.Union[typing.Sequence["ErrorList"], "LocError"]


class LocError(utility.Representation):
    """Error with a location."""

    exc: Exception
    loc: Loc

    def __init__(self, exc: Exception, loc: typing.Union[str, Loc] = "__root__") -> None:
        self.exc = exc
        self.loc = loc if isinstance(loc, tuple) else (loc,)


class ValidationError(utility.Representation, ValueError):
    """Pretty validation error inspired by pydantic."""

    errors: typing.Sequence[LocError]
    model: typing.Type[apimodel.APIModel]

    def __init__(self, errors: typing.Collection[ErrorList], model: typing.Type[apimodel.APIModel]) -> None:
        self.errors = typing.cast("typing.Sequence[LocError]", utility.flatten_sequences(*errors))
        self.model = model

    def __str__(self) -> str:
        errors = list(flatten_errors(self.errors))
        return (
            f'{len(errors)} validation error{"" if len(errors) == 1 else "s"} for {self.model.__name__}\n'
            + "\n".join(f'{" -> ".join(str(e) for e in loc)}\n  {msg}' for loc, msg in errors)
        )


def flatten_errors(
    errors: typing.Sequence[ErrorList],
    loc: typing.Optional[Loc] = None,
) -> typing.Iterator[typing.Tuple[Loc, str]]:
    """Flatten recursive errors."""
    for error in errors:
        if isinstance(error, LocError):
            error_loc = error.loc
            if loc:
                error_loc = loc + error_loc

            if isinstance(error.exc, ValidationError):
                yield from flatten_errors(error.exc.errors, error_loc)
            else:
                yield (error_loc, str(error.exc))

        else:
            yield from flatten_errors(error, loc=loc)


def maybe_raise_error(*errors: ErrorList, model: typing.Any) -> None:
    """Raise errors if any."""
    if errors:
        raise ValidationError(errors, model)
