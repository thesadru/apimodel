"""Model generator from JSON data."""
from __future__ import annotations

import collections
import datetime
import json
import sys
import typing

from . import tutils

__all__ = ["generate_models"]

JSONType = typing.Union[None, str, int, float, bool, typing.Sequence["JSONType"], typing.Mapping[str, "JSONType"]]
"""Raw JSON."""
RawSchemaType = typing.Union[str, typing.Sequence["RawSchemaType"], typing.Mapping[str, "RawSchemaType"]]
"""Raw schema type."""
SchemaType = typing.Mapping[
    str, typing.Tuple[typing.Union[str, typing.Sequence[str]], typing.MutableMapping[str, typing.Any]]
]
"""Output schema type. `{name: (type, field)}`."""

T = typing.TypeVar("T")


def to_pascal_case(string: str) -> str:
    """Turn snake case into pascal case."""
    return "".join(x[:1].upper() + x[1:] for x in string.split("_"))


def to_snake_case(string: str) -> str:
    """Turn pascal case into snake case."""
    return "".join("_" + x.lower() if x.isupper() else x for x in string)


def format_object(values: typing.Union[str, typing.Sequence[str]]) -> str:
    """Format a union."""
    if isinstance(values, str):
        return values

    values, old_values = [x for x in values if "None" not in x], values

    if "[]" in values[0]:
        genalias = values.pop(0).replace("[]", "")
        if len(values) == 1:
            genalias = genalias + "[{}]"
        elif len(values) != len(old_values):
            genalias = genalias + "[typing.Optional[{}]]"
        else:
            genalias = genalias + "[typing.Union[{}]]"
    else:
        if len(values) != len(old_values):
            genalias = "typing.Optional[{}]"
        else:
            genalias = "typing.Union[{}]"

    return genalias.format(", ".join(values))


def flatten_list(values: typing.Sequence[tutils.MaybeSequence[T]]) -> typing.Sequence[T]:
    """Flatten a possibly recursive list."""
    new: typing.Sequence[T] = []

    for value in values:
        if isinstance(value, typing.Sequence) and not isinstance(value, str):
            new += flatten_list(typing.cast("typing.Sequence[T]", value))
        else:
            new.append(typing.cast("T", value))

    return new


def join_union(raw_values: typing.Sequence[T]) -> tutils.MaybeSequence[T]:
    """Join a union with an emphasis on mappings."""
    values = flatten_list(raw_values)
    values = tuple({repr(tp): tp for tp in values}.values())
    if "float" in values:
        values = [x for x in values if x != "int"]

    if all(isinstance(value, typing.Mapping) for value in values):
        values = typing.cast("typing.Sequence[typing.Mapping[str, T]]", values)
        mapping: typing.Mapping[str, tutils.MaybeSequence[T]] = {}
        for index, value in enumerate(values):
            for k, v in value.items():
                mapping[k] = join_union([mapping.get(k, v if index == 0 else "None"), v])

        return typing.cast("T", mapping)

    if len(values) == 1:
        return values[0]

    return values


def recognize_json_type(value: JSONType) -> RawSchemaType:
    """Recognize JSON type of value."""
    if value in tutils.NoneTypes:
        return "None"

    if isinstance(value, str):
        try:
            datetime.datetime.fromisoformat(value)
        except ValueError:
            return "str"
        else:
            return "datetime.datetime"

    if isinstance(value, typing.Sequence):
        values = [recognize_json_type(item) for item in value]
        values.insert(0, "typing.Sequence[]")
        return join_union(values)

    if isinstance(value, typing.Mapping):
        return {name: recognize_json_type(item) for name, item in value.items()}

    return type(value).__name__


def add_schema(
    schema_name: str,
    raw_schema: typing.Mapping[str, RawSchemaType],
    schemas: typing.MutableMapping[str, SchemaType],
) -> SchemaType:
    """Add schema to a collection of previous schemas."""
    schema: SchemaType = {}

    for name, value in raw_schema.items():
        data: typing.MutableMapping[str, typing.Any] = {}
        name, old_name = to_snake_case(name), name
        if name != old_name:
            data["name"] = '"' + old_name + '"'

        if isinstance(value, typing.Sequence) and not isinstance(value, str):
            union: typing.Sequence[str] = []
            for x in value:
                if isinstance(x, typing.Mapping):
                    unique_name = to_pascal_case(schema_name + "_" + name)
                    add_schema(unique_name, x, schemas)
                    union.append(unique_name)
                else:
                    union.append(typing.cast(str, x))

            schema[name] = (join_union(union), data)

        elif isinstance(value, typing.Mapping):
            unique_name = to_pascal_case(schema_name + "_" + name)
            add_schema(unique_name, value, schemas)
            schema[name] = unique_name, data

        else:
            schema[name] = value, data

    if not schema_name:
        schema_name = "Root"

    schemas[schema_name] = schema
    return schema


def create_schemas(data: JSONType) -> typing.Mapping[str, SchemaType]:
    """Create raw schemas from json data."""
    raw_schema = recognize_json_type(data)
    if isinstance(raw_schema, typing.Sequence):
        raw_schema = {"root": raw_schema}

    schemas: typing.MutableMapping[str, SchemaType] = collections.OrderedDict()
    add_schema("", raw_schema, schemas)

    return schemas


def generate_models(data: JSONType) -> str:
    """Generate model code from data."""
    schemas = create_schemas(data)

    code = "import typing\n\nimport apimodel\n\n"

    for schema_name, schema in schemas.items():
        code += f"class {schema_name}(apimodel.APIModel):\n"
        for name, (value, data) in schema.items():
            value = format_object(value)

            code += f"    {name}: {value}"
            if "Optional" in value:
                data["default"] = "None"

            if data:
                code += " = "
                if "default" in data and len(data) == 1:
                    code += data["default"]
                else:
                    args = ([data.pop("default")] if "default" in data else []) + [f"{k}={v}" for k, v in data.items()]
                    code += f"apimodel.Field({', '.join(args)})"

            code += "\n"

        code += "\n\n"

    return code.strip() + "\n"


if __name__ == "__main__":
    sys.stdout.write(generate_models(json.load(sys.stdin)))
