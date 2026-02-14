"""Reference resolution and section schema extraction."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .model_types import OperationSpec


class ResolveError(RuntimeError):
    """Raised when resolving OpenAPI references fails."""


_HTTP_SUCCESS_PREFIX = "2"


@dataclass(frozen=True)
class SectionSchemas:
    """Resolved section schemas for one endpoint operation."""

    url_params: dict[str, Any] | None
    query_params: dict[str, Any] | None
    headers: dict[str, Any] | None
    cookies: dict[str, Any] | None
    body: dict[str, Any] | None
    response_schemas: dict[str, dict[str, Any]]
    error_schemas: dict[str, dict[str, Any]]


class Resolver:
    """Resolve local references and build endpoint section schemas."""

    def __init__(self, document: dict[str, Any]) -> None:
        self._document = deepcopy(document)
        self._cache: dict[str, Any] = {}
        self._cycle_cache: set[str] = set()

    def resolve_node(self, node: Any) -> Any:
        """Recursively inline references in a node."""
        return self._resolve(node, stack=())

    def _resolve(self, node: Any, stack: tuple[str, ...]) -> Any:
        if isinstance(node, list):
            return [self._resolve(item, stack) for item in node]
        if not isinstance(node, dict):
            return node

        ref_value = node.get("$ref")
        if isinstance(ref_value, str):
            resolved_ref = self._resolve_ref(ref_value, stack)
            siblings = {key: value for key, value in node.items() if key != "$ref"}
            if siblings:
                merged = deepcopy(resolved_ref)
                for key, value in siblings.items():
                    merged[key] = self._resolve(value, stack)
                return self._resolve(merged, stack)
            return deepcopy(resolved_ref)

        return {key: self._resolve(value, stack) for key, value in node.items()}

    def _resolve_ref(self, ref: str, stack: tuple[str, ...]) -> Any:
        if ref in stack:
            # Keep recursive structures representable without infinite expansion.
            self._cycle_cache.add(ref)
            return {"$ref": ref}

        if ref in self._cache:
            return deepcopy(self._cache[ref])

        if not ref.startswith("#/"):
            raise ResolveError(f"Only local references are currently supported: {ref}")

        current: Any = self._document
        for token in ref[2:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(current, dict) or token not in current:
                raise ResolveError(f"Unresolvable reference: {ref}")
            current = current[token]

        resolved = self._resolve(deepcopy(current), (*stack, ref))
        self._cache[ref] = deepcopy(resolved)
        return resolved

    def build_section_schemas(self, operation_spec: OperationSpec) -> SectionSchemas:
        """Build all section schemas for a single operation."""
        path_params = self._collect_parameters(operation_spec.path_item)
        operation_params = self._collect_parameters(operation_spec.operation)

        merged_params = [*path_params, *operation_params]

        url_schema = self._parameters_to_schema(merged_params, location="path")
        query_schema = self._parameters_to_schema(merged_params, location="query")
        header_schema = self._parameters_to_schema(merged_params, location="header")
        cookie_schema = self._parameters_to_schema(merged_params, location="cookie")

        request_body = operation_spec.operation.get("requestBody")
        body_schema = self._request_body_to_schema(request_body)

        responses_raw = operation_spec.operation.get("responses")
        success: dict[str, dict[str, Any]] = {}
        errors: dict[str, dict[str, Any]] = {}
        if isinstance(responses_raw, dict):
            for status_code, response_node in responses_raw.items():
                if not isinstance(status_code, str):
                    continue
                schema = self._response_to_schema(response_node)
                if schema is None:
                    continue
                target = success if status_code.startswith(_HTTP_SUCCESS_PREFIX) else errors
                target[status_code] = schema

        return SectionSchemas(
            url_params=url_schema,
            query_params=query_schema,
            headers=header_schema,
            cookies=cookie_schema,
            body=body_schema,
            response_schemas=success,
            error_schemas=errors,
        )

    def _collect_parameters(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        raw = node.get("parameters")
        if not isinstance(raw, list):
            return []
        parameters: list[dict[str, Any]] = []
        for parameter in raw:
            if not isinstance(parameter, dict):
                continue
            resolved = self.resolve_node(parameter)
            if isinstance(resolved, dict):
                parameters.append(resolved)
        return parameters

    def _parameters_to_schema(
        self,
        parameters: list[dict[str, Any]],
        *,
        location: str,
    ) -> dict[str, Any] | None:
        properties: dict[str, Any] = {}
        required: list[str] = []

        for parameter in parameters:
            if parameter.get("in") != location:
                continue
            name = parameter.get("name")
            if not isinstance(name, str) or not name:
                continue

            schema: dict[str, Any]
            schema_node = parameter.get("schema")
            if isinstance(schema_node, dict):
                resolved_schema = self.resolve_node(schema_node)
                schema = resolved_schema if isinstance(resolved_schema, dict) else {}
            else:
                schema = {"type": "string"}

            for doc_key in (
                "description",
                "deprecated",
                "example",
                "examples",
                "contentMediaType",
                "contentEncoding",
            ):
                if doc_key in parameter and doc_key not in schema:
                    schema[doc_key] = deepcopy(parameter[doc_key])

            properties[name] = schema
            if bool(parameter.get("required")):
                required.append(name)

        if not properties:
            return None

        schema_obj: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "required": sorted(set(required)),
            "additionalProperties": False,
        }
        return schema_obj

    def _request_body_to_schema(self, request_body: Any) -> dict[str, Any] | None:
        if not isinstance(request_body, dict):
            return None
        resolved_body = self.resolve_node(request_body)
        if not isinstance(resolved_body, dict):
            return None
        content = resolved_body.get("content")
        if not isinstance(content, dict):
            return None

        preferred_media_types = (
            "application/json",
            "application/*+json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        )

        candidates: list[dict[str, Any]] = []
        for media_type in preferred_media_types:
            media = content.get(media_type)
            if isinstance(media, dict):
                candidates.append(media)
        for media in content.values():
            if isinstance(media, dict) and media not in candidates:
                candidates.append(media)

        for media in candidates:
            schema_node = media.get("schema")
            if isinstance(schema_node, dict):
                resolved_schema = self.resolve_node(schema_node)
                if isinstance(resolved_schema, dict):
                    return resolved_schema
        return None

    def _response_to_schema(self, response_node: Any) -> dict[str, Any] | None:
        if not isinstance(response_node, dict):
            return None
        resolved_response = self.resolve_node(response_node)
        if not isinstance(resolved_response, dict):
            return None

        content = resolved_response.get("content")
        if not isinstance(content, dict):
            return None

        preferred_media_types = (
            "application/json",
            "application/*+json",
            "application/problem+json",
            "application/x-www-form-urlencoded",
        )

        candidates: list[dict[str, Any]] = []
        for media_type in preferred_media_types:
            media = content.get(media_type)
            if isinstance(media, dict):
                candidates.append(media)
        for media in content.values():
            if isinstance(media, dict) and media not in candidates:
                candidates.append(media)

        for media in candidates:
            schema_node = media.get("schema")
            if isinstance(schema_node, dict):
                resolved_schema = self.resolve_node(schema_node)
                if isinstance(resolved_schema, dict):
                    return resolved_schema
        return None
