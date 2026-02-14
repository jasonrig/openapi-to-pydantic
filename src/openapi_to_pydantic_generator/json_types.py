"""JSON-compatible typing aliases shared across the project."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Union

type JSONPrimitive = Union[str, int, float, bool, None]
type JSONValue = JSONPrimitive | list[JSONValue] | Mapping[str, JSONValue]
type JSONObject = Mapping[str, JSONValue]
type MutableJSONObject = dict[str, JSONValue]
type JSONMapping = Mapping[str, JSONValue]
