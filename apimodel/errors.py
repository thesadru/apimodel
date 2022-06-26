"""Pretty errors."""
from __future__ import annotations

import contextlib
import typing

from . import apimodel, tutils, utility

__all__ = ["LocError", "ValidationError", "catch_errors"]


Loc = typing.Tuple[typing.Union[int, str], ...]
RawLoc = typing.Union[int, str, Loc]
ErrorList = typing.Union[typing.Sequence["ErrorList"], "LocError"]


class LocError(utility.Representation, Exception):
    """Error with a location."""

    error: Exception
    """Original error."""

    loc: Loc
    """Location where the error ocurred."""

    def __init__(self, error: Exception, loc: RawLoc = "__root__") -> None:
        """Initialize a LocError.

        The instance will act as an intersection between LocError and the passed error.
        """
        self.error = error
        self.loc = loc if isinstance(loc, tuple) else (loc,)

        super().__init__(str(error))

    def __instancecheck__(self, instance: typing.Any) -> bool:
        return isinstance(instance, self.error.__class__)


class ValidationError(utility.Representation, ValueError):
    """Pretty validation error inspired by pydantic."""

    errors: typing.Sequence[LocError]
    """Collected errors."""

    model: typing.Type[apimodel.APIModel]
    """The model in which the error ocurred. Used for debugging."""

    def __init__(self, *errors: ErrorList, model: typing.Type[apimodel.APIModel]) -> None:
        """Initialize a ValidationError with a list of LocErrors."""
        self.errors = utility.flatten_sequences(*errors)
        self.model = model

        super().__init__(self.errors)

    def __str__(self) -> str:
        errors = list(flatten_errors(self.errors))
        return (
            f'{len(errors)} validation error{"" if len(errors) == 1 else "s"} for {self.model.__name__}\n'
            + "\n".join(f'{" -> ".join(map(str, loc))}\n  {error.__class__.__name__}: {error}' for loc, error in errors)
        )

    @property
    def locations(self) -> typing.Sequence[typing.Tuple[Loc, Exception]]:
        """Get flattened locations and errors."""
        return list(flatten_errors(self.errors))


def flatten_errors(
    errors: typing.Sequence[ErrorList],
    loc: typing.Optional[Loc] = None,
) -> typing.Iterator[typing.Tuple[Loc, Exception]]:
    """Flatten recursive errors."""
    for error in errors:
        if isinstance(error, LocError):
            error_loc = error.loc
            if loc:
                error_loc = loc + error_loc

            if isinstance(error.error, ValidationError):
                yield from flatten_errors(error.error.errors, loc=error_loc)
            else:
                yield (error_loc, error.error)

        else:
            yield from flatten_errors(error, loc=loc)


class ErrorCatcher:
    """Catch errors and append to a list."""

    __slots__ = ("errors", "model")

    errors: typing.MutableSequence[LocError]
    model: typing.Type[apimodel.APIModel]

    def __init__(self, model: tutils.MaybeType[apimodel.APIModel]) -> None:
        """Initialize an ErrorCatcher."""
        if not isinstance(model, type):
            model = type(model)

        self.errors = []
        self.model = model

    def add_error(self, error: Exception, loc: RawLoc) -> None:
        """Add an error to the list."""
        self.errors.append(LocError(error, loc))

    @contextlib.contextmanager
    def catch(self, loc: RawLoc = "__root__") -> typing.Iterator[None]:
        """Catch errors and append to a list."""
        try:
            yield
        except Exception as e:
            self.errors.append(LocError(e, loc))

    def __enter__(self) -> typing.ContextManager[None]:
        return self.catch()

    def raise_errors(self) -> None:
        """Raise errors."""
        if self.errors:
            raise ValidationError(self.errors, model=self.model)


@contextlib.contextmanager
def catch_errors(model: tutils.MaybeType[apimodel.APIModel]) -> typing.Iterator[ErrorCatcher]:
    """Catch errors and raise a ValidationError if at least one is present.

    Examples
    --------
    >>> with apimodel.errors.catch_errors(model) as catcher:
    >>>     for name, function in function:
    >>>         with catcher.catch(loc=function.__name__):
    >>>             function()
    """
    if not isinstance(model, type):
        model = type(model)

    catcher = ErrorCatcher(model)
    try:
        yield catcher
    finally:
        catcher.raise_errors()
