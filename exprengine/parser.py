"""Recursive-descent / precedence-climbing parser.

Produces the AST defined in :mod:`exprengine.ast_nodes` from the token stream.
The parser is a pure function of its tokens (no shared state), matching the
precedence table in the spec:

    sequence ';'  <  assignment '='  <  ternary '?:'  <  or  <  and
    <  == !=  <  < <= > >=  <  + -  <  * / // %  <  unary not - +
    <  ** (right-assoc)  <  call f(...)  <  primary
"""

from __future__ import annotations

from . import lexer as L
from .ast_nodes import (
    Assignment,
    BinaryOp,
    Call,
    Lambda,
    Literal,
    Logical,
    Node,
    Sequence,
    Ternary,
    UnaryOp,
    Variable,
)
from .errors import ParseError
from .lexer import Token

_COMPARISON = {L.LT: "<", L.LE: "<=", L.GT: ">", L.GE: ">="}
_ADDITIVE = {L.PLUS: "+", L.MINUS: "-"}
_MULTIPLICATIVE = {L.STAR: "*", L.SLASH: "/", L.DSLASH: "//", L.PERCENT: "%"}
_EQUALITY = {L.EQ: "==", L.NE: "!="}


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    # --- token helpers -----------------------------------------------------
    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def _peek_type(self, offset: int = 0) -> str:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return L.EOF
        return self.tokens[idx].type

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, type_: str, what: str) -> Token:
        if self.current.type != type_:
            raise ParseError(
                f"expected {what} but found {self._describe(self.current)}",
                self.current.position,
            )
        return self._advance()

    @staticmethod
    def _describe(tok: Token) -> str:
        if tok.type == L.EOF:
            return "end of input"
        return repr(tok.value)

    # --- entry point -------------------------------------------------------
    def parse(self) -> Node:
        node = self._sequence()
        if self.current.type != L.EOF:
            raise ParseError(
                f"unexpected {self._describe(self.current)}", self.current.position
            )
        return node

    # --- grammar -----------------------------------------------------------
    def _sequence(self) -> Node:
        start = self.current.position
        statements = [self._statement()]
        while self.current.type == L.SEMICOLON:
            self._advance()
            # Allow a trailing ';' before EOF or ')'
            if self.current.type in (L.EOF, L.RPAREN):
                break
            statements.append(self._statement())
        if len(statements) == 1:
            return statements[0]
        return Sequence(statements, start)

    def _statement(self) -> Node:
        # Assignment: IDENT '=' expression  (single '=', not '==')
        if self.current.type == L.IDENT and self._peek_type(1) == L.ASSIGN:
            name_tok = self._advance()
            self._advance()  # consume '='
            value = self._expression()
            return Assignment(name_tok.value, value, name_tok.position)
        return self._expression()

    def _expression(self) -> Node:
        return self._ternary()

    def _ternary(self) -> Node:
        cond = self._logic_or()
        if self.current.type == L.QUESTION:
            pos = self._advance().position
            then = self._expression()
            self._expect(L.COLON, "':' in ternary expression")
            otherwise = self._expression()
            return Ternary(cond, then, otherwise, pos)
        return cond

    def _logic_or(self) -> Node:
        node = self._logic_and()
        while self.current.type == L.OR:
            pos = self._advance().position
            node = Logical("or", node, self._logic_and(), pos)
        return node

    def _logic_and(self) -> Node:
        node = self._equality()
        while self.current.type == L.AND:
            pos = self._advance().position
            node = Logical("and", node, self._equality(), pos)
        return node

    def _equality(self) -> Node:
        node = self._comparison()
        while self.current.type in _EQUALITY:
            tok = self._advance()
            node = BinaryOp(_EQUALITY[tok.type], node, self._comparison(), tok.position)
        return node

    def _comparison(self) -> Node:
        node = self._additive()
        while self.current.type in _COMPARISON:
            tok = self._advance()
            node = BinaryOp(_COMPARISON[tok.type], node, self._additive(), tok.position)
        return node

    def _additive(self) -> Node:
        node = self._multiplicative()
        while self.current.type in _ADDITIVE:
            tok = self._advance()
            node = BinaryOp(_ADDITIVE[tok.type], node, self._multiplicative(), tok.position)
        return node

    def _multiplicative(self) -> Node:
        node = self._unary()
        while self.current.type in _MULTIPLICATIVE:
            tok = self._advance()
            node = BinaryOp(_MULTIPLICATIVE[tok.type], node, self._unary(), tok.position)
        return node

    def _unary(self) -> Node:
        if self.current.type in (L.NOT, L.MINUS, L.PLUS):
            tok = self._advance()
            op = {"NOT": "not", "MINUS": "-", "PLUS": "+"}[tok.type]
            return UnaryOp(op, self._unary(), tok.position)
        return self._power()

    def _power(self) -> Node:
        base = self._postfix()
        if self.current.type == L.DSTAR:
            pos = self._advance().position
            # right-associative; right side is unary so 2 ** -3 parses
            exponent = self._unary()
            return BinaryOp("**", base, exponent, pos)
        return base

    def _postfix(self) -> Node:
        node = self._primary()
        while self.current.type == L.LPAREN:
            pos = self.current.position
            args = self._argument_list()
            node = Call(node, args, pos)
        return node

    def _argument_list(self) -> list[Node]:
        self._expect(L.LPAREN, "'('")
        args: list[Node] = []
        if self.current.type != L.RPAREN:
            args.append(self._expression())
            while self.current.type == L.COMMA:
                self._advance()
                args.append(self._expression())
        self._expect(L.RPAREN, "')' to close argument list")
        return args

    def _primary(self) -> Node:
        tok = self.current
        t = tok.type

        if t == L.NUMBER:
            self._advance()
            return Literal(tok.value, tok.position)
        if t == L.STRING:
            self._advance()
            return Literal(tok.value, tok.position)
        if t in (L.TRUE, L.FALSE, L.NULL):
            self._advance()
            return Literal(tok.value, tok.position)
        if t == L.IDENT:
            self._advance()
            return Variable(tok.value, tok.position)
        if t == L.LPAREN:
            return self._lambda_or_group()

        raise ParseError(
            f"unexpected {self._describe(tok)}; expected a value or '('", tok.position
        )

    def _lambda_or_group(self) -> Node:
        """A '(' may open a lambda parameter list or a parenthesized group.

        We optimistically try to parse a lambda header ``( params ) =>``;
        on any mismatch we backtrack and parse a normal group.
        """
        start = self.pos
        lparen_pos = self.current.position
        lam = self._try_parse_lambda(lparen_pos)
        if lam is not None:
            return lam
        self.pos = start  # backtrack
        self._expect(L.LPAREN, "'('")
        expr = self._expression()
        self._expect(L.RPAREN, "')' to close group")
        return expr

    def _try_parse_lambda(self, lparen_pos: int) -> Node | None:
        self._advance()  # consume '('
        params: list[str] = []
        if self.current.type == L.IDENT:
            params.append(self._advance().value)
            while self.current.type == L.COMMA:
                self._advance()
                if self.current.type != L.IDENT:
                    return None
                params.append(self._advance().value)
        elif self.current.type != L.RPAREN:
            return None  # not a parameter list
        if self.current.type != L.RPAREN:
            return None
        self._advance()  # consume ')'
        if self.current.type != L.ARROW:
            return None
        self._advance()  # consume '=>'
        body = self._expression()
        return Lambda(params, body, lparen_pos)


def parse(source: str) -> Node:
    """Tokenize and parse ``source`` into an AST."""
    return Parser(L.tokenize(source)).parse()
