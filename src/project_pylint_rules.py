"""Custom pylint rules for project typing policy."""

from __future__ import annotations

from collections.abc import Iterable

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter


_MESSAGE_PREFER_OPTIONAL = "prefer-optional"
_MESSAGE_NO_OBJECT_ANNOTATION = "no-object-annotation"


class ProjectRulesChecker(BaseChecker):
    """Project-specific AST checks."""

    name = "project-rules"

    msgs = {
        "C9501": (
            "Use Optional[T] instead of T | None in annotations",
            _MESSAGE_PREFER_OPTIONAL,
            "Project style requires Optional[T] for nullable annotations.",
        ),
        "C9502": (
            "Avoid object in type annotations; use a more specific type",
            _MESSAGE_NO_OBJECT_ANNOTATION,
            "Project style avoids object annotations when a better type exists.",
        ),
    }

    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        """Validate annotation style for annotated assignments.

        Args:
            node (nodes.AnnAssign): Assignment node to inspect.
        """
        self._check_annotation(node.annotation)

    def visit_arguments(self, node: nodes.Arguments) -> None:
        """Validate annotation style for function arguments.

        Args:
            node (nodes.Arguments): Function arguments node to inspect.
        """
        for annotation in self._iter_argument_annotations(node):
            self._check_annotation(annotation)

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Validate annotation style for function return type.

        Args:
            node (nodes.FunctionDef): Function definition node to inspect.
        """
        if node.returns is not None:
            self._check_annotation(node.returns)

    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None:
        """Validate annotation style for async function return type.

        Args:
            node (nodes.AsyncFunctionDef): Async function definition node to inspect.
        """
        if node.returns is not None:
            self._check_annotation(node.returns)

    def _check_annotation(self, annotation: nodes.NodeNG) -> None:
        for optional_union in self._iter_optional_pipe_unions(annotation):
            self.add_message(_MESSAGE_PREFER_OPTIONAL, node=optional_union)
        for object_name in self._iter_object_annotations(annotation):
            self.add_message(_MESSAGE_NO_OBJECT_ANNOTATION, node=object_name)

    @staticmethod
    def _iter_argument_annotations(arguments: nodes.Arguments) -> Iterable[nodes.NodeNG]:
        for annotation in arguments.posonlyargs_annotations:
            if annotation is not None:
                yield annotation
        for annotation in arguments.annotations:
            if annotation is not None:
                yield annotation
        for annotation in arguments.kwonlyargs_annotations:
            if annotation is not None:
                yield annotation
        if arguments.varargannotation is not None:
            yield arguments.varargannotation
        if arguments.kwargannotation is not None:
            yield arguments.kwargannotation

    @staticmethod
    def _iter_optional_pipe_unions(annotation: nodes.NodeNG) -> Iterable[nodes.BinOp]:
        for candidate in annotation.nodes_of_class(nodes.BinOp):
            if candidate.op != "|":
                continue
            if _is_none_literal(candidate.left) or _is_none_literal(candidate.right):
                yield candidate

    @staticmethod
    def _iter_object_annotations(annotation: nodes.NodeNG) -> Iterable[nodes.Name]:
        for candidate in annotation.nodes_of_class(nodes.Name):
            if candidate.name == "object":
                yield candidate


def _is_none_literal(node: nodes.NodeNG) -> bool:
    return isinstance(node, nodes.Const) and node.value is None


def register(linter: PyLinter) -> None:
    """Register checker.

    Args:
        linter (PyLinter): Pylint linter instance.
    """
    linter.register_checker(ProjectRulesChecker(linter))
