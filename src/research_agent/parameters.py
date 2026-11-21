"""JSON Schema construction and validation for registered scalar parameters."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from research_agent.llm.base import JsonObject

type FieldType = Literal["string", "integer", "number", "boolean"]


class InvalidArguments(ValueError):
    """Arguments do not match the declared tool parameter constraints."""


@dataclass(frozen=True)
class Parameter:
    kind: FieldType
    description: str
    required: bool = True
    min_length: int | None = None
    max_length: int | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None

    def schema(self) -> JsonObject:
        schema: JsonObject = {"type": self.kind, "description": self.description}
        for name, value in (
            ("minLength", self.min_length),
            ("maxLength", self.max_length),
            ("minimum", self.minimum),
            ("maximum", self.maximum),
        ):
            if value is not None:
                schema[name] = value
        return schema

    def validate(self, name: str, value: object) -> None:
        if self.kind == "string" and isinstance(value, str):
            if self.min_length is not None and len(value) < self.min_length:
                raise InvalidArguments(f"{name} is too short")
            if self.max_length is not None and len(value) > self.max_length:
                raise InvalidArguments(f"{name} is too long")
            return
        if self.kind == "boolean" and type(value) is bool:
            return
        # A JSON boolean is distinct from a JSON number.
        integer = type(value) is int
        finite_float = type(value) is float and isfinite(value)
        if (self.kind == "integer" and integer) or (self.kind == "number" and (integer or finite_float)):
            if self.minimum is not None and value < self.minimum:
                raise InvalidArguments(f"{name} is below the minimum")
            if self.maximum is not None and value > self.maximum:
                raise InvalidArguments(f"{name} is above the maximum")
            return
        raise InvalidArguments(f"{name} must be a {self.kind}")


def parameter_schema(parameters: Mapping[str, Parameter]) -> JsonObject:
    return {
        "type": "object",
        "properties": {name: field.schema() for name, field in parameters.items()},
        "required": [name for name, field in parameters.items() if field.required],
        "additionalProperties": False,
    }


def validate_arguments(parameters: Mapping[str, Parameter], arguments: object) -> None:
    if not isinstance(arguments, dict):
        raise InvalidArguments("Arguments must be an object")
    if arguments.keys() - parameters.keys():
        raise InvalidArguments("Arguments contain undeclared fields")
    for name, field in parameters.items():
        if name in arguments:
            field.validate(name, arguments[name])
        elif field.required:
            raise InvalidArguments(f"{name} is required")
