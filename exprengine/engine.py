"""Public engine: compile-then-evaluate, with a thread-safe LRU compile cache.

Usage::

    import exprengine
    expr = exprengine.compile("2 + 3 * (x - 1)")   # parse + compile once
    expr.evaluate({"x": 4})                          # -> 11, call millions of times

The expensive work (lex + parse + compile-to-closures) happens once per unique
source string and is cached. ``CompiledExpression.evaluate`` is the hot path: it
allocates a fresh scope chain and invokes the pre-built closure. Compiled
expressions are immutable and share only read-only state, so the same object can
be evaluated concurrently from many threads without locking.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Callable

from .ast_nodes import EvalFn
from .builtins import DEFAULT_CONSTANTS, DEFAULT_FUNCTIONS
from .parser import parse
from .values import Scope

_DEFAULT_CACHE_SIZE = 1024


class CompiledExpression:
    """An immutable, reusable, thread-safe compiled expression."""

    __slots__ = ("_fn", "source", "_base_scope")

    def __init__(self, fn: EvalFn, source: str, base_scope: Scope) -> None:
        self._fn = fn
        self.source = source
        self._base_scope = base_scope  # read-only: builtins + engine namespace

    def evaluate(self, variables: dict[str, Any] | None = None) -> Any:
        """Evaluate against ``variables``. Names absent here and in the engine
        namespace raise ``UndefinedVariableError`` (strict)."""
        # var_scope wraps the caller's dict read-only (we never mutate it);
        # `local` absorbs any top-level `x = ...` assignments. Fresh per call
        # => concurrent evaluations never share mutable state.
        var_scope = Scope(variables if variables is not None else {}, self._base_scope)
        local = Scope({}, var_scope)
        return self._fn(local)

    def __call__(self, variables: dict[str, Any] | None = None) -> Any:
        return self.evaluate(variables)

    def __repr__(self) -> str:  # pragma: no cover
        return f"CompiledExpression({self.source!r})"


class _LRUCache:
    """A tiny thread-safe LRU cache for compiled expressions."""

    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._data: "OrderedDict[str, CompiledExpression]" = OrderedDict()
        self._lock = threading.Lock()

    def get_or_compile(self, source: str, compile_fn: Callable[[str], CompiledExpression]) -> CompiledExpression:
        with self._lock:
            hit = self._data.get(source)
            if hit is not None:
                self._data.move_to_end(source)
                return hit
        # Compile outside the lock (pure work); a rare duplicate compile under
        # contention is harmless since the result is identical.
        compiled = compile_fn(source)
        with self._lock:
            existing = self._data.get(source)
            if existing is not None:
                self._data.move_to_end(source)
                return existing
            self._data[source] = compiled
            if self._maxsize and len(self._data) > self._maxsize:
                self._data.popitem(last=False)
        return compiled

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class Engine:
    """Factory for compiled expressions with a shared namespace and cache.

    Extra ``functions`` (Python callables) and ``constants`` are merged over the
    built-in math namespace and become available to every expression this engine
    compiles.
    """

    def __init__(
        self,
        functions: dict[str, Callable[..., Any]] | None = None,
        constants: dict[str, Any] | None = None,
        cache_size: int = _DEFAULT_CACHE_SIZE,
    ) -> None:
        namespace: dict[str, Any] = {}
        namespace.update(DEFAULT_CONSTANTS)
        namespace.update(DEFAULT_FUNCTIONS)
        if constants:
            namespace.update(constants)
        if functions:
            namespace.update(functions)
        # One shared read-only base scope reused by every compiled expression.
        self._base_scope = Scope(namespace)
        self._cache = _LRUCache(cache_size)

    def compile(self, source: str) -> CompiledExpression:
        """Compile ``source`` (cached). Raises ``ParseError`` on bad syntax."""
        return self._cache.get_or_compile(source, self._compile_uncached)

    def _compile_uncached(self, source: str) -> CompiledExpression:
        ast = parse(source)
        fn = ast.compile()
        return CompiledExpression(fn, source, self._base_scope)

    def evaluate(self, source: str, variables: dict[str, Any] | None = None) -> Any:
        """Convenience: compile (cached) then evaluate in one call."""
        return self.compile(source).evaluate(variables)

    def clear_cache(self) -> None:
        self._cache.clear()


# --- Module-level default engine & convenience API -------------------------

_default_engine = Engine()


def compile(source: str) -> CompiledExpression:  # noqa: A001 - intentional public name
    """Compile ``source`` using the default engine (built-in math namespace)."""
    return _default_engine.compile(source)


def evaluate(source: str, variables: dict[str, Any] | None = None) -> Any:
    """Compile (cached) and evaluate ``source`` using the default engine."""
    return _default_engine.evaluate(source, variables)
