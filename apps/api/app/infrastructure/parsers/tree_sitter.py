"""Tree-sitter wrapper.

Uses pre-built grammars from `tree-sitter-languages` so we don't compile
grammars per platform. Exposes:
  - parse(source, language) -> Tree
  - extract_symbols(source, language) -> list[SymbolSpan]

Symbol extraction uses tree-sitter Query DSL per language, capturing function /
class / method definitions with their byte ranges. Languages we don't ship a
query for produce zero symbols (the file still gets line-window chunks).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

try:
    from tree_sitter import Parser, Tree
    from tree_sitter_languages import get_language
except Exception:  # pragma: no cover — surface a friendly error if deps missing
    Parser = None  # type: ignore[assignment]
    Tree = None  # type: ignore[assignment]
    get_language = None  # type: ignore[assignment]

from app.domain.repositories.models import SymbolKind


@dataclass(slots=True, frozen=True)
class SymbolSpan:
    kind: SymbolKind
    name: str
    qualified_name: str
    start_line: int     # 1-based inclusive
    end_line: int       # 1-based inclusive
    signature: str | None = None


_QUERIES: Final[dict[str, str]] = {
    "python": """
        (function_definition name: (identifier) @name) @function
        (class_definition name: (identifier) @name) @class
    """,
    "javascript": """
        (function_declaration name: (identifier) @name) @function
        (method_definition name: (property_identifier) @name) @method
        (class_declaration name: (identifier) @name) @class
        (lexical_declaration
          (variable_declarator
            name: (identifier) @name
            value: [(arrow_function) (function_expression)])) @function
    """,
    "typescript": """
        (function_declaration name: (identifier) @name) @function
        (method_definition name: (property_identifier) @name) @method
        (class_declaration name: (type_identifier) @name) @class
        (interface_declaration name: (type_identifier) @name) @interface
        (lexical_declaration
          (variable_declarator
            name: (identifier) @name
            value: [(arrow_function) (function_expression)])) @function
    """,
    "go": """
        (function_declaration name: (identifier) @name) @function
        (method_declaration name: (field_identifier) @name) @method
        (type_declaration (type_spec name: (type_identifier) @name)) @class
    """,
    "rust": """
        (function_item name: (identifier) @name) @function
        (struct_item name: (type_identifier) @name) @class
        (impl_item type: (type_identifier) @name) @method
        (trait_item name: (type_identifier) @name) @interface
    """,
    "java": """
        (method_declaration name: (identifier) @name) @method
        (class_declaration name: (identifier) @name) @class
        (interface_declaration name: (identifier) @name) @interface
    """,
    "cpp": """
        (function_definition declarator: (function_declarator
          declarator: (identifier) @name)) @function
        (class_specifier name: (type_identifier) @name) @class
    """,
    "c": """
        (function_definition declarator: (function_declarator
          declarator: (identifier) @name)) @function
    """,
}


_KIND_FROM_CAPTURE: Final[dict[str, SymbolKind]] = {
    "function": SymbolKind.function,
    "method": SymbolKind.method,
    "class": SymbolKind.class_,
    "interface": SymbolKind.interface,
}


_parser_cache: dict[str, Parser] = {}


def _get_parser(language: str) -> Parser | None:
    if Parser is None or get_language is None:
        return None
    cached = _parser_cache.get(language)
    if cached is not None:
        return cached
    try:
        lang = get_language(language)
    except Exception:
        return None
    parser = Parser()
    parser.set_language(lang)
    _parser_cache[language] = parser
    return parser


def parse(source: bytes, language: str) -> Tree | None:
    parser = _get_parser(language)
    if parser is None:
        return None
    return parser.parse(source)


def extract_symbols(
    *,
    source: bytes,
    language: str,
    file_path: str,
) -> list[SymbolSpan]:
    """Run the per-language query and produce SymbolSpans."""
    if language not in _QUERIES:
        return []
    parser = _get_parser(language)
    if parser is None:
        return []
    tree = parser.parse(source)
    try:
        query = get_language(language).query(_QUERIES[language])  # type: ignore[union-attr]
    except Exception:
        return []

    # Captures look like: [(node, 'name'), (node, 'function'), ...]
    # We pair each "@name" with the next non-name capture (its container).
    captures = query.captures(tree.root_node)
    spans: list[SymbolSpan] = []
    pending_name: tuple[str, int, int] | None = None  # (name, start_line, end_line)
    for node, capture_name in captures:
        if capture_name == "name":
            try:
                pending_name = (
                    source[node.start_byte : node.end_byte].decode("utf-8", errors="replace"),
                    node.start_point[0] + 1,
                    node.end_point[0] + 1,
                )
            except Exception:
                pending_name = None
        elif capture_name in _KIND_FROM_CAPTURE and pending_name is not None:
            kind = _KIND_FROM_CAPTURE[capture_name]
            name, _name_start, _name_end = pending_name
            start = node.start_point[0] + 1
            end = node.end_point[0] + 1
            qualified = f"{file_path}::{name}"
            spans.append(
                SymbolSpan(
                    kind=kind,
                    name=name,
                    qualified_name=qualified,
                    start_line=start,
                    end_line=end,
                )
            )
            pending_name = None
    return spans
