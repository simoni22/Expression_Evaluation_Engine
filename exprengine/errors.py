"""Exception hierarchy for the expression engine.

The hierarchy is intentionally shallow and public: consumers of the library
(other backend teams) can catch ``ExpressionError`` to handle *anything* this
engine raises, or catch a specific subclass for finer control.

    ExpressionError
    ├── ParseError              (lexing / parsing — bad syntax)
    └── EvaluationError         (runtime — something went wrong while evaluating)
        ├── UndefinedVariableError
        ├── ExpressionTypeError     (strict-typing violation)
        ├── DivisionByZeroError
        └── FunctionError           (not callable / wrong arity)
"""

from __future__ import annotations


class ExpressionError(Exception):
    """Base class for every error raised by the engine."""


class ParseError(ExpressionError):
    """Raised during lexing or parsing when the source is malformed.

    Carries the 1-based ``position`` (character offset) of the problem in the
    source string so callers can point users at the exact spot.
    """

    def __init__(self, message: str, position: int | None = None) -> None:
        self.position = position
        if position is not None:
            message = f"{message} (at position {position})"
        super().__init__(message)


class EvaluationError(ExpressionError):
    """Base class for errors raised while evaluating a compiled expression."""


class UndefinedVariableError(EvaluationError):
    """A name was referenced that is not defined in the scope or host context.

    This is the *undefined* half of "null and undefined": the name is absent
    entirely. We raise (strict mode) rather than silently defaulting, which is
    the core defense against the "always evaluates to 0" footgun.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"undefined variable or function: '{name}'")


class ExpressionTypeError(EvaluationError):
    """An operator or function received operand types it does not accept.

    Raised under strict typing, e.g. ``"3" + 4``, ``1 + true``, or arithmetic
    on a ``null`` value.
    """


class DivisionByZeroError(EvaluationError):
    """Division or modulo by zero. We never silently produce inf/nan."""


class FunctionError(EvaluationError):
    """A call target is not callable, or was called with the wrong arity."""
