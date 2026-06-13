"""Lexer: turns a source string into a flat list of tokens.

Tokens carry their source ``position`` (0-based index of their first char) so
the parser and error messages can point precisely at problems. The lexer is a
pure function of its input and holds no shared state, so it is trivially
thread-safe.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from .errors import ParseError

# --- Token types -----------------------------------------------------------
# Literals / names
NUMBER = "NUMBER"
STRING = "STRING"
IDENT = "IDENT"
# Keyword operators / literals
AND = "AND"
OR = "OR"
NOT = "NOT"
TRUE = "TRUE"
FALSE = "FALSE"
NULL = "NULL"
# Punctuation / operators
PLUS = "PLUS"
MINUS = "MINUS"
STAR = "STAR"
SLASH = "SLASH"
DSLASH = "DSLASH"        # //
PERCENT = "PERCENT"
DSTAR = "DSTAR"          # **
EQ = "EQ"                # ==
NE = "NE"                # !=
LT = "LT"
LE = "LE"
GT = "GT"
GE = "GE"
ASSIGN = "ASSIGN"        # =
ARROW = "ARROW"          # =>
QUESTION = "QUESTION"    # ?
COLON = "COLON"          # :
SEMICOLON = "SEMICOLON"  # ;
COMMA = "COMMA"
LPAREN = "LPAREN"
RPAREN = "RPAREN"
EOF = "EOF"

_KEYWORDS = {
    "and": AND,
    "or": OR,
    "not": NOT,
    "true": TRUE,
    "false": FALSE,
    "null": NULL,
}


class Token(NamedTuple):
    type: str
    value: Any
    position: int


def tokenize(source: str) -> list[Token]:
    """Tokenize ``source`` into a list ending with an ``EOF`` token."""
    tokens: list[Token] = []
    i = 0
    n = len(source)

    while i < n:
        ch = source[i]

        # Whitespace
        if ch in " \t\r\n":
            i += 1
            continue

        start = i

        # Numbers: integer or float (with optional fractional / exponent part)
        if ch.isdigit() or (ch == "." and i + 1 < n and source[i + 1].isdigit()):
            i, value = _read_number(source, i)
            tokens.append(Token(NUMBER, value, start))
            continue

        # Strings: single or double quoted, with escape support
        if ch == '"' or ch == "'":
            i, value = _read_string(source, i)
            tokens.append(Token(STRING, value, start))
            continue

        # Identifiers / keywords
        if ch.isalpha() or ch == "_":
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
            word = source[start:i]
            kw = _KEYWORDS.get(word)
            if kw is not None:
                literal = {"true": True, "false": False, "null": None}.get(word, word)
                tokens.append(Token(kw, literal, start))
            else:
                tokens.append(Token(IDENT, word, start))
            continue

        # Operators / punctuation (longest match first)
        two = source[i : i + 2]
        if two == "**":
            tokens.append(Token(DSTAR, "**", start)); i += 2; continue
        if two == "//":
            tokens.append(Token(DSLASH, "//", start)); i += 2; continue
        if two == "==":
            tokens.append(Token(EQ, "==", start)); i += 2; continue
        if two == "!=":
            tokens.append(Token(NE, "!=", start)); i += 2; continue
        if two == "<=":
            tokens.append(Token(LE, "<=", start)); i += 2; continue
        if two == ">=":
            tokens.append(Token(GE, ">=", start)); i += 2; continue
        if two == "=>":
            tokens.append(Token(ARROW, "=>", start)); i += 2; continue

        single = {
            "+": PLUS, "-": MINUS, "*": STAR, "/": SLASH, "%": PERCENT,
            "=": ASSIGN, "<": LT, ">": GT, "?": QUESTION, ":": COLON,
            ";": SEMICOLON, ",": COMMA, "(": LPAREN, ")": RPAREN,
        }.get(ch)
        if single is not None:
            tokens.append(Token(single, ch, start)); i += 1; continue

        if ch == "!":
            raise ParseError("unexpected '!' (did you mean '!='?)", start)
        raise ParseError(f"unexpected character {ch!r}", start)

    tokens.append(Token(EOF, None, n))
    return tokens


def _read_number(source: str, i: int) -> tuple[int, Any]:
    start = i
    n = len(source)
    saw_dot = False
    saw_exp = False
    while i < n:
        c = source[i]
        if c.isdigit():
            i += 1
        elif c == "." and not saw_dot and not saw_exp:
            saw_dot = True
            i += 1
        elif c in "eE" and not saw_exp:
            saw_exp = True
            i += 1
            if i < n and source[i] in "+-":
                i += 1
        else:
            break
    text = source[start:i]
    if saw_dot or saw_exp:
        return i, float(text)
    return i, int(text)


def _read_string(source: str, i: int) -> tuple[int, str]:
    quote = source[i]
    start = i
    i += 1
    n = len(source)
    out: list[str] = []
    escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "0": "\0"}
    while i < n:
        c = source[i]
        if c == "\\":
            if i + 1 >= n:
                raise ParseError("unterminated escape in string", i)
            nxt = source[i + 1]
            out.append(escapes.get(nxt, nxt))
            i += 2
            continue
        if c == quote:
            return i + 1, "".join(out)
        out.append(c)
        i += 1
    raise ParseError("unterminated string literal", start)
