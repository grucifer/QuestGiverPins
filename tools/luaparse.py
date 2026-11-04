"""Tiny Lua expression parser/evaluator for data-only Lua (tables, constants, arithmetic).
Never executes anything; unknown identifiers/calls raise or are resolved via an env dict."""
import re

class LuaError(Exception):
    pass

class Nil:
    pass

TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<lcomment>--\[(?P<leq>=*)\[.*?\](?P=leq)\])
  | (?P<comment>--[^\n]*)
  | (?P<lstr>\[(?P<seq>=*)\[.*?\](?P=seq)\])
  | (?P<num>0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)
  | (?P<str>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\.\.\.|\.\.|==|~=|<=|>=|[{}\[\]().,;=+\-*/%^#<>:])
""", re.S | re.X)

KEYWORDS = {"and", "or", "not", "nil", "true", "false", "function", "end", "local",
            "return", "if", "then", "else", "elseif", "for", "while", "do", "repeat", "until", "in", "break"}

def tokenize(src):
    toks = []
    pos = 0
    n = len(src)
    while pos < n:
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise LuaError("bad char at %d: %r" % (pos, src[pos:pos + 30]))
        pos = m.end()
        k = m.lastgroup
        if k in ("ws", "comment", "lcomment"):
            continue
        if k == "leq" or k == "seq":
            k = "lstr" if m.group("lstr") else "lcomment"
            if k == "lcomment":
                continue
        if m.group("lstr") is not None:
            s = m.group("lstr")
            eq = len(m.group("seq"))
            body = s[2 + eq:-(2 + eq)]
            if body.startswith("\n"):
                body = body[1:]
            toks.append(("str", body))
        elif k == "num":
            t = m.group("num")
            v = int(t, 16) if t.lower().startswith("0x") else (float(t) if any(c in t for c in ".eE") else int(t))
            toks.append(("num", v))
        elif k == "str":
            toks.append(("str", unescape(m.group("str")[1:-1])))
        elif k == "name":
            t = m.group("name")
            toks.append(("kw", t) if t in KEYWORDS else ("name", t))
        else:
            toks.append(("op", m.group("op")))
    toks.append(("eof", None))
    return toks

def unescape(s):
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            d = s[i + 1]
            mp = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "a": "\a", "b": "\b", "\n": "\n"}
            if d in mp:
                out.append(mp[d]); i += 2; continue
            if d.isdigit():
                j = i + 1
                while j < len(s) and j < i + 4 and s[j].isdigit():
                    j += 1
                out.append(chr(int(s[i + 1:j]))); i = j; continue
            out.append(d); i += 2; continue
        out.append(c); i += 1
    return "".join(out)


class LuaTable(dict):
    """dict keyed by python values; positional entries use int keys 1..n."""
    pass


class Parser:
    def __init__(self, toks, env, on_unknown=None):
        self.t = toks
        self.i = 0
        self.env = env
        self.on_unknown = on_unknown

    def peek(self, k=0):
        return self.t[self.i + k]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expect(self, kind, val=None):
        tok = self.next()
        if tok[0] != kind or (val is not None and tok[1] != val):
            raise LuaError("expected %s %s got %r near token %d" % (kind, val, tok, self.i))
        return tok

    def accept(self, kind, val=None):
        tok = self.peek()
        if tok[0] == kind and (val is None or tok[1] == val):
            self.i += 1
            return True
        return False

    # precedence climbing
    BINPREC = {"or": 1, "and": 2, "<": 3, ">": 3, "<=": 3, ">=": 3, "~=": 3, "==": 3,
               "..": 5, "+": 6, "-": 6, "*": 7, "/": 7, "%": 7, "^": 10}

    def expr(self, limit=0):
        tok = self.peek()
        if (tok[0] == "kw" and tok[1] == "not") or (tok[0] == "op" and tok[1] in ("-", "#")):
            self.next()
            v = self.expr(8)
            if tok[1] == "not":
                left = not truthy(v)
            elif tok[1] == "-":
                left = -num(v)
            else:
                left = len(v) if isinstance(v, str) else seqlen(v)
        else:
            left = self.simple()
        while True:
            tok = self.peek()
            op = tok[1] if tok[0] in ("op", "kw") else None
            prec = self.BINPREC.get(op)
            if prec is None or prec <= limit:
                break
            self.next()
            rprec = prec - 1 if op in ("..", "^") else prec
            if op == "and":
                right = self.expr(rprec)
                left = right if truthy(left) else left
                continue
            if op == "or":
                right = self.expr(rprec)
                left = left if truthy(left) else right
                continue
            right = self.expr(rprec)
            left = binop(op, left, right)
        return left

    def simple(self):
        tok = self.next()
        k, v = tok
        if k == "num" or k == "str":
            return v
        if k == "kw":
            if v == "nil":
                return None
            if v == "true":
                return True
            if v == "false":
                return False
            if v == "function":
                self.skip_function_body()
                return None
            raise LuaError("unexpected keyword %s" % v)
        if k == "op" and v == "{":
            return self.table()
        if k == "op" and v == "(":
            e = self.expr()
            self.expect("op", ")")
            return self.suffixes(e, None)
        if k == "name":
            path = [v]
            if v in self.env:
                val = self.env[v]
            else:
                val = UNKNOWN
            return self.suffixes(val, path)
        raise LuaError("unexpected token %r at %d" % (tok, self.i))

    def suffixes(self, val, path):
        while True:
            tok = self.peek()
            if tok == ("op", "."):
                self.next()
                name = self.expect("name")[1]
                if path is not None:
                    path = path + [name]
                val = index(val, name, path, self.on_unknown)
            elif tok == ("op", "[") :
                self.next()
                key = self.expr()
                self.expect("op", "]")
                val = index(val, key, path, self.on_unknown)
                path = None
            elif tok[0] == "op" and tok[1] in ("(", ":") or tok[0] == "str" or tok == ("op", "{"):
                selfarg = []
                fname = ".".join(path) if path else "?"
                if tok[1] == ":":
                    self.next()
                    mname = self.expect("name")[1]
                    selfarg = [val]
                    fname += ":" + mname
                    val = index(val, mname, path, self.on_unknown) if isinstance(val, dict) else UNKNOWN
                args = self.call_args()
                if callable(val):
                    val = val(*(selfarg + args))
                elif fname.endswith("l10n") and args:
                    val = args[0]  # data-only: l10n("x") -> "x"
                else:
                    val = None
                path = None
            else:
                break
        if val is UNKNOWN:
            if self.on_unknown:
                return self.on_unknown(path)
            raise LuaError("unknown identifier %s" % ".".join(path or ["?"]))
        return val

    def call_args(self):
        tok = self.peek()
        if tok[0] == "str":
            self.next(); return [tok[1]]
        if tok == ("op", "{"):
            self.next(); return [self.table()]
        self.expect("op", "(")
        args = []
        if not self.accept("op", ")"):
            args.append(self.expr())
            while self.accept("op", ","):
                args.append(self.expr())
            self.expect("op", ")")
        return args

    def table(self):
        t = LuaTable()
        n = 1
        while not self.accept("op", "}"):
            tok = self.peek()
            if tok == ("op", "["):
                self.next()
                key = self.expr()
                self.expect("op", "]")
                self.expect("op", "=")
                val = self.expr()
                if val is not None:
                    t[key] = val
            elif tok[0] == "name" and self.peek(1) == ("op", "="):
                self.next(); self.next()
                val = self.expr()
                if val is not None:
                    t[tok[1]] = val
            else:
                val = self.expr()
                if val is not None:
                    t[n] = val
                n += 1
            if not (self.accept("op", ",") or self.accept("op", ";")):
                self.expect("op", "}")
                break
        return t

    def skip_function_body(self):
        depth = 1
        while depth:
            k, v = self.next()
            if k == "eof":
                raise LuaError("eof in function")
            if k == "kw" and v in ("function", "if", "do"):
                depth += 1
            elif k == "kw" and v == "end":
                depth -= 1
            # 'while'/'for' use 'do' which we count; 'repeat' uses until
            elif k == "kw" and v == "repeat":
                depth += 1
            elif k == "kw" and v == "until":
                depth -= 1


class _Unknown:
    def __repr__(self):
        return "UNKNOWN"
UNKNOWN = _Unknown()

def index(val, key, path, on_unknown):
    if val is UNKNOWN:
        return UNKNOWN
    if isinstance(val, dict):
        if key in val:
            return val[key]
        if isinstance(key, float) and key.is_integer() and int(key) in val:
            return val[int(key)]
        if hasattr(val, "missing"):
            return val.missing(key)
        return None
    if val is None:
        raise LuaError("index nil with %r (path %s)" % (key, path))
    raise LuaError("index non-table %r" % (val,))

def truthy(v):
    return v is not None and v is not False

def num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise LuaError("arith on %r" % (v,))
    return v

def binop(op, a, b):
    if op == "..":
        return fmt(a) + fmt(b)
    if op in ("==", "~="):
        r = a == b
        return r if op == "==" else not r
    if op in ("<", ">", "<=", ">="):
        return {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]
    a, b = num(a), num(b)
    if op == "+": r = a + b
    elif op == "-": r = a - b
    elif op == "*": r = a * b
    elif op == "/": r = a / b
    elif op == "%": r = a % b
    elif op == "^": r = float(a) ** b
    if isinstance(r, float) and r.is_integer() and op != "/":
        r = int(r)
    return r

def fmt(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)

def seqlen(t):
    n = 0
    while (n + 1) in t:
        n += 1
    return n

def seq(t):
    """Return list form of positional part of a LuaTable (with None holes up to max int key)."""
    if t is None:
        return []
    ks = [k for k in t if isinstance(k, int) and k >= 1]
    if not ks:
        return []
    return [t.get(i) for i in range(1, max(ks) + 1)]


def parse_expr_at(src, start_pattern, env, on_unknown=None):
    """Find regex start_pattern in source; parse a Lua expression right after its end."""
    m = re.search(start_pattern, src)
    if not m:
        raise LuaError("pattern not found: " + start_pattern)
    toks = tokenize(src[m.end():])
    return Parser(toks, env, on_unknown).expr()

def eval_expr(src, env=None, on_unknown=None):
    return Parser(tokenize(src), env or {}, on_unknown).expr()
