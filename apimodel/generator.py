"""Model generator from JSON data."""
from __future__ import annotations

import sys
import typing

from . import parser, tutils, utility

__all__ = ["generate_models"]

JSONType = typing.Union[None, str, int, float, bool, typing.Sequence["JSONType"], typing.Mapping[str, "JSONType"]]
RawSchema = typing.Union[
    str,
    typing.Tuple["RawSchema", ...],
    typing.List["RawSchema"],
    typing.Mapping[str, "RawSchema"],
]

MaybeUnion = tutils.MaybeSequence[str]
Field = typing.TypedDict("Field", {"name": str, "type": MaybeUnion, "default": object, "array": bool}, total=False)
Schema = typing.Mapping[str, Field]

VersionInfo = typing.Union[typing.Tuple[int, ...], "sys._version_info"]

T = typing.TypeVar("T")


def to_pascal_case(string: str) -> str:
    """Turn snake case into pascal case."""
    return "".join(x[:1].upper() + x[1:] for x in string.split("_"))


def to_snake_case(string: str) -> str:
    """Turn camel case into snake case."""
    return "".join(
        ("_" if i and string[i].isupper() and not string[i : i + 2].isupper() else "") + x.lower()  # noqa: E203
        for i, x in enumerate(string)
    )


def format_field_type(
    field: typing.Union[str, Field],
    *,
    python: typing.Optional[VersionInfo] = None,
) -> str:
    """Format a field type."""
    if isinstance(field, str):
        return field

    assert "type" in field, "Incomplete Field"
    python = python or sys.version_info

    types: typing.Sequence[str]
    optional: bool = False

    if not isinstance(field["type"], str):  # union
        types, old_types = [x for x in field["type"] if "None" not in x], field["type"]
        if len(types) != len(old_types):
            optional = True
    elif field["type"] == "None":
        types = ("object",)
        optional = True
    else:
        types = (field["type"],)

    if python >= (3, 10):
        annotation = " | ".join(types)
        if optional:
            annotation += " | None"
    else:
        if len(types) == 1:
            annotation = types[0]
        else:
            annotation = f"typing.Union[{', '.join(types)}]"

        if optional:
            annotation = f"typing.Optional[{annotation}]"

    if field.get("array", False):
        if python >= (3, 9):
            annotation = f"list[{annotation}]"
        else:
            annotation = f"typing.Sequence[{annotation}]"

    return annotation


def format_field_default(field: Field) -> str:
    """Format a field default."""
    data = {k: v for k, v in field.items() if k not in ("type", "array", "default")}

    if "default" in field and not data:
        return str(field["default"])

    args: typing.Sequence[str] = []
    if "default" in field:
        args = [str(field["default"])]

    args += [f"{k}={v}" for k, v in data.items()]

    if not args:
        return ""

    return f"apimodel.Field({', '.join(args)})"


def join_union(raw_values: typing.Sequence[T]) -> tutils.MaybeTuple[T]:
    """Join a union with an emphasis on mappings.

    Return a tuple if there are multiple values.
    """
    values = utility.flatten_sequences(raw_values)
    values = tuple({repr(tp): tp for tp in values}.values())
    if "float" in values:
        values = tuple(x for x in values if x != "int")

    if values and all(isinstance(value, typing.Mapping) for value in values):
        values = typing.cast("typing.Sequence[typing.Mapping[str, T]]", values)
        mapping: typing.Mapping[str, tutils.MaybeTuple[T]] = {}
        for index, value in enumerate(values):
            for k, v in value.items():
                new_v = join_union((mapping.get(k, v if index == 0 else "None"), v))
                if isinstance(v, list) and (k not in mapping or isinstance(mapping[k], list)):
                    new_v = list(typing.cast("tuple[object, ...]", new_v)) if isinstance(new_v, tuple) else [new_v]

                mapping[k] = new_v

        return typing.cast("T", mapping)

    if len(values) == 1:
        return values[0]

    return values


def recognize_json_type(value: JSONType) -> RawSchema:
    """Recognize JSON type of value."""
    if value in tutils.NoneTypes:
        return "None"

    if isinstance(value, str):
        try:
            parser.datetime_validator.synchronous(NotImplemented, value)
        except (ValueError, TypeError, OSError):
            return "str"
        else:
            return "datetime.datetime"

    if isinstance(value, typing.Sequence):
        values = [recognize_json_type(item) for item in value]
        clean = join_union(values)
        return list(clean) if isinstance(clean, tuple) else [clean]

    if isinstance(value, typing.Mapping):
        return {name: recognize_json_type(item) for name, item in value.items()}

    return type(value).__name__


def add_schema(
    schema_name: str,
    raw_schema: typing.Mapping[str, RawSchema],
    schemas: typing.MutableMapping[str, Schema],
) -> Schema:
    """Add schema to a collection of previous schemas."""
    schema: Schema = {}

    for name, value in raw_schema.items():
        field: Field = {}

        name, old_name = to_snake_case(name), name
        if name != old_name:
            field["name"] = '"' + old_name + '"'

        # tuple = union, list = array of union
        if isinstance(value, list):
            field["array"] = True
            if len(value) == 1:
                value = value[0]

        if isinstance(value, typing.Sequence) and not isinstance(value, str):
            union: typing.Sequence[str] = []
            for x in value:
                if isinstance(x, typing.Mapping):
                    unique_name = to_pascal_case(schema_name + "_" + name)
                    add_schema(unique_name, x, schemas)
                    union.append(unique_name)
                else:
                    union.append(typing.cast(str, x))

            field["type"] = join_union(union)
            schema[name] = field

        elif isinstance(value, typing.Mapping):
            unique_name = to_pascal_case(schema_name + "_" + name)
            add_schema(unique_name, value, schemas)

            field["type"] = unique_name
            schema[name] = field

        else:
            field["type"] = value
            schema[name] = field

        if "None" in field.get("type", ""):
            field["default"] = "None"

    if not schema_name:
        schema_name = "Root"

    schemas[schema_name] = schema
    return schema


def create_schemas(data: JSONType) -> typing.Mapping[str, Schema]:
    """Create raw schemas from json data."""
    raw_schema = recognize_json_type(data)
    if isinstance(raw_schema, typing.Sequence):
        raw_schema = {"field": raw_schema}

    schemas: typing.MutableMapping[str, Schema] = {}
    add_schema("", raw_schema, schemas)

    return schemas


def generate_models(
    data: JSONType,
    *,
    python: typing.Optional[VersionInfo] = None,
) -> str:
    """Generate model code from data."""
    schemas = create_schemas(data)

    code = "import typing\n\nimport apimodel\n\n"

    for schema_name, schema in schemas.items():
        code += f"class {schema_name}(apimodel.APIModel):\n"
        if len(schema) == 0:
            code += "    pass\n"

        for name, field in schema.items():
            value = format_field_type(field, python=python)
            default = format_field_default(field)

            code += f"    {name}: {value}"
            if default:
                code += " = " + default

            code += "\n"

        code += "\n\n"

    return code.strip() + "\n"
