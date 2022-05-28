import datetime
import sys
import typing

import pytest

import apimodel


@pytest.fixture()
def model() -> apimodel.APIModel:
    """Dummy model with no validation."""
    return apimodel.APIModel({})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime.datetime(2010, 1, 1), datetime.datetime(2010, 1, 1, tzinfo=datetime.timezone.utc)),
        ("2011-01-01T00:00:00", datetime.datetime(2011, 1, 1, tzinfo=datetime.timezone.utc)),
        ("2012-01-01T00:00:00Z", datetime.datetime(2012, 1, 1, tzinfo=datetime.timezone.utc)),
        (1356998400, datetime.datetime(2013, 1, 1, tzinfo=datetime.timezone.utc)),
    ],
)
def test_datetime_validator(model: apimodel.APIModel, value: typing.Any, expected: datetime.datetime) -> typing.Any:
    assert apimodel.parser.datetime_validator(model, value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime.timedelta(seconds=1), datetime.timedelta(seconds=1)),
        (2, datetime.timedelta(seconds=2)),
    ],
)
def test_timedelta_validator(model: apimodel.APIModel, value: typing.Any, expected: datetime.timedelta) -> typing.Any:
    assert apimodel.parser.timedelta_validator(model, value) == expected


def test_noop_validator(model: apimodel.APIModel) -> typing.Any:
    value = object()
    assert apimodel.parser.noop_validator(model, value) == value


@pytest.mark.parametrize(
    ("callback", "value", "expected"),
    [
        (str, "foo", "foo"),
        (int, "42", 42),
    ],
)
def test_cast_validator(
    model: apimodel.APIModel,
    callback: typing.Callable[[typing.Any], typing.Any],
    value: typing.Any,
    expected: typing.Any,
) -> typing.Any:
    assert apimodel.parser.cast_validator(callback)(model, value) == expected


@pytest.mark.parametrize(
    ("tp", "value", "expected"),
    [
        (str, "foo", "foo"),
        (int, 42, 42),
    ],
)
def test_arbitrary_validator(
    model: apimodel.APIModel,
    tp: typing.Type[typing.Any],
    value: typing.Any,
    expected: typing.Any,
) -> typing.Any:
    assert apimodel.parser.arbitrary_validator(tp)(model, value) == expected


@pytest.mark.parametrize(
    ("values", "value", "expected"),
    [
        (["foo", "bar"], "foo", "foo"),
        ([1, 2], 1, 1),
    ],
)
def test_literal_validator(
    model: apimodel.APIModel,
    values: typing.Collection[typing.Any],
    value: typing.Any,
    expected: typing.Any,
) -> typing.Any:
    assert apimodel.parser.literal_validator(values)(model, value) == expected


@pytest.mark.parametrize(
    ("collection_type", "inner_validator", "value", "expected"),
    [
        (typing.List[str], apimodel.parser.cast_validator(str), ["foo", "bar"], ["foo", "bar"]),
        (typing.Sequence[int], apimodel.parser.cast_validator(int), {1, 2}, (1, 2)),
        (typing.Set[bool], apimodel.parser.cast_validator(bool), [0, 1], frozenset({False, True})),
        (
            typing.MutableSet[typing.Any] if sys.version_info >= (3, 9) else typing.Set[typing.Any],
            apimodel.parser.noop_validator,
            ["foo", 1],
            {"foo", 1},
        ),
    ],
)
def test_collection_validator(
    model: apimodel.APIModel,
    collection_type: typing.Type[typing.Any],
    inner_validator: apimodel.Validator,
    value: typing.Any,
    expected: typing.Any,
) -> typing.Any:
    assert apimodel.parser.collection_validator(collection_type, inner_validator)(model, value) == expected


@pytest.mark.parametrize(
    ("mapping_type", "key_validator", "value_validator", "value", "expected"),
    [
        (
            typing.Dict[str, str],
            apimodel.parser.cast_validator(str),
            apimodel.parser.cast_validator(str),
            {"foo": "bar"},
            {"foo": "bar"},
        ),
    ],
)
def test_mapping_validator(
    model: apimodel.APIModel,
    mapping_type: typing.Type[typing.Any],
    key_validator: apimodel.Validator,
    value_validator: apimodel.Validator,
    value: typing.Any,
    expected: typing.Any,
) -> typing.Any:
    assert apimodel.parser.mapping_validator(mapping_type, key_validator, value_validator)(model, value) == expected


@pytest.mark.parametrize(
    ("validators", "value", "expected"),
    [
        ([apimodel.parser.noop_validator, apimodel.parser.noop_validator], "foo", "foo"),
        ([apimodel.parser.literal_validator(["foo"]), apimodel.parser.cast_validator(int)], "42", 42),
    ],
)
def test_union_validator(
    model: apimodel.APIModel,
    validators: typing.List[apimodel.Validator],
    value: typing.Any,
    expected: typing.Any,
) -> typing.Any:
    assert apimodel.parser.union_validator(validators)(model, value) == expected


@pytest.mark.parametrize(
    ("tp", "value", "expected"),
    [
        (typing.Any, "foo", "foo"),
        (int, "42", 42),
        (typing.Union[int, float], "4.2", 4.2),
        (typing.Annotated[object, typing.Any] if sys.version_info >= (3, 9) else typing.Any, "foo", "foo"),
        (typing.TypeVar("T", bound=str), 42, "42"),
    ],
)
def test_cast(tp: typing.Type[typing.Any], value: typing.Any, expected: typing.Any) -> typing.Any:
    assert apimodel.parser.cast(tp, value) == expected
