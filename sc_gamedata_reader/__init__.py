"""Read Lua data without executing it. CC0-1.0."""
from .parser import parse_file, parse_text
from .contract import FORMAT_VERSION, CALL_FORMAT_VERSION, ParseResult, iter_assignments, iter_calls, table_get

__all__ = ["parse_file", "parse_text", "FORMAT_VERSION", "ParseResult",
           "iter_assignments", "iter_calls", "CALL_FORMAT_VERSION", "table_get"]
