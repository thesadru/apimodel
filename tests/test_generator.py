import typing

import pytest

import apimodel


@pytest.mark.parametrize(
    ("string", "pascal"),
    [
        ("snake_case", "SnakeCase"),
        ("PascalCase", "PascalCase"),
        ("camelCase", "CamelCase"),
        ("random_CASE", "RandomCASE"),
        ("UPPER_CASE", "UPPERCASE"),
        ("", ""),
    ],
)
def test_to_pascal_case(string: str, pascal: str) -> None:
    assert apimodel.generator.to_pascal_case(string) == pascal


@pytest.mark.parametrize(
    ("string", "snake"),
    [
        ("snake_case", "snake_case"),
        ("PascalCase", "pascal_case"),
        ("camelCase", "camel_case"),
        ("random_CASE", "random_case"),
        ("UPPER_CASE", "upper_case"),
    ],
)
def test_to_snake_case(string: str, snake: str) -> None:
    assert apimodel.generator.to_snake_case(string) == snake


@pytest.fixture()
def json_data() -> typing.Any:
    return {
        "string": "foo",
        "integer": 42,
        "boolean": True,
        "null": None,
        "timestamp": "2020-01-01T00:00:00Z",
        "array": [1, 2, 3],
        "nested": {
            "string": "foo",
            "integer": 42,
        },
        "nestedArray": [
            {"maybeFloat": 42.0, "any": "foo"},
            {"maybeFloat": None, "any": 42},
            {"maybeFloat": 42, "any": None},
        ],
    }


def test_create_schemas(json_data: typing.Any) -> None:
    schemas = apimodel.generator.create_schemas(json_data)

    assert schemas == {
        "Root": {
            "string": {"type": "str"},
            "integer": {"type": "int"},
            "boolean": {"type": "bool"},
            "null": {"type": "None", "default": "None"},
            "timestamp": {"type": "datetime.datetime"},
            "array": {"array": True, "type": "int"},
            "nested": {"type": "Nested"},
            "nested_array": {"array": True, "type": "NestedArray", "alias": '"nestedArray"'},
        },
        "Nested": {
            "string": {"type": "str"},
            "integer": {"type": "int"},
        },
        "NestedArray": {
            "maybe_float": {"type": ("float", "None"), "alias": '"maybeFloat"', "default": "None"},
            "any": {"type": ("str", "int", "None"), "default": "None"},
        },
    }


def test_generate_models(json_data: typing.Any) -> None:
    code = apimodel.generator.generate_models(json_data, python=(3, 10))
    expected = """
import typing

import apimodel

class Nested(apimodel.APIModel):
    string: str
    integer: int


class NestedArray(apimodel.APIModel):
    maybe_float: float | None = apimodel.Field(None, alias="maybeFloat")
    any: str | int | None = None


class Root(apimodel.APIModel):
    string: str
    integer: int
    boolean: bool
    null: object | None = None
    timestamp: datetime.datetime
    array: list[int]
    nested: Nested
    nested_array: list[NestedArray] = apimodel.Field(alias="nestedArray")
""".lstrip()
    assert code == expected
