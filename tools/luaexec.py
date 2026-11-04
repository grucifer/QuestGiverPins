"""Minimal statement walker for data-definition Lua files (no loops, no real calls)."""
from luaparse import tokenize, Parser, LuaError, LuaTable, UNKNOWN, index

class Func:
    def __init__(self, toks, start, end, params):
        self.toks, self.start, self.end, self.params = toks, start, end, params

class Interp:
    def __init__(self, env, on_unknown=None, verbose=False):
        self.env = env  # global scope (dict)
        self.unknowns = {}
        def _rec(path):
            k = ".".join(path or ["?"])
            self.unknowns[k] = self.unknowns.get(k, 0) + 1
            return None
        self.on_unknown = on_unknown or _rec
        self.functions = {}  # "Module:Method" -> Func
        self.verbose = verbose
        self.warnings = []

    def run_file(self, src):
        toks = tokenize(src)
        p = Parser(toks, self.env, self.on_unknown)
        return self.block(p, self.env, stop=("eof",))

    def call(self, fname, scope=None):
        f = self.functions[fname]
        p = Parser(f.toks, None, self.on_unknown)
        p.i = f.start
        local = ChainEnv(scope or self.env)
        p.env = local
        return self.block(p, local, stop=("end",))

    # returns ("return", value) or None
    def block(self, p, env, stop):
        while True:
            tok = p.peek()
            if tok[0] == "eof" or (tok[0] == "kw" and tok[1] in stop) or (tok[0] == "kw" and tok[1] in ("end", "else", "elseif")):
                return None
            r = self.statement(p, env)
            if r is not None:
                return r

    def skip_block_to_end(self, p):
        depth = 1
        while depth:
            k, v = p.next()
            if k == "eof":
                raise LuaError("eof while skipping")
            if k == "kw" and v in ("function", "if", "do", "repeat"):
                depth += 1
            elif k == "kw" and v in ("end", "until"):
                depth -= 1

    def statement(self, p, env):
        tok = p.peek()
        if tok == ("op", ";"):
            p.next(); return None
        if tok[0] == "kw":
            kw = tok[1]
            if kw == "local":
                p.next()
                if p.accept("kw", "function"):
                    p.expect("name"); self.skip_block_to_end(p); return None
                names = [p.expect("name")[1]]
                while p.accept("op", ","):
                    names.append(p.expect("name")[1])
                vals = []
                if p.accept("op", "="):
                    vals = self.exprlist(p, env)
                for i, n in enumerate(names):
                    env.set_local(n, vals[i] if i < len(vals) else None) if isinstance(env, ChainEnv) else env.__setitem__(n, vals[i] if i < len(vals) else None)
                return None
            if kw == "function":
                p.next()
                name = p.expect("name")[1]
                while p.peek()[0] == "op" and p.peek()[1] in (".", ":"):
                    sep = p.next()[1]
                    name += sep + p.expect("name")[1]
                p.expect("op", "(")
                params = []
                while not p.accept("op", ")"):
                    t = p.next()
                    if t[0] == "name":
                        params.append(t[1])
                start = p.i
                self.skip_block_to_end(p)
                self.functions[name.split(".")[-1] if ":" not in name else name] = Func(p.t, start, p.i - 1, params)
                return None
            if kw == "return":
                p.next()
                if p.peek()[0] == "eof" or p.peek() == ("kw", "end"):
                    return ("return", None)
                vals = self.exprlist(p, env)
                return ("return", vals[0] if vals else None)
            if kw == "if":
                p.next()
                taken = False
                result = None
                while True:
                    try:
                        cond = p.expr()
                    except LuaError:
                        cond = False
                    p.expect("kw", "then")
                    if not taken and cond is not None and cond is not False and cond is not UNKNOWN:
                        taken = True
                        result = self.block(p, env, stop=())
                        # skip rest
                        if p.peek()[0] == "kw" and p.peek()[1] in ("else", "elseif"):
                            # skip remaining branches
                            self.skip_block_to_end(p)
                            return result
                        p.expect("kw", "end")
                        return result
                    else:
                        self.skip_branch(p)
                    t = p.next()
                    if t == ("kw", "elseif"):
                        continue
                    if t == ("kw", "else"):
                        result = self.block(p, env, stop=())
                        p.expect("kw", "end")
                        return result
                    if t == ("kw", "end"):
                        return None
                    raise LuaError("bad if: %r" % (t,))
            if kw in ("for", "while"):
                p.next()
                while p.next() != ("kw", "do"):
                    pass
                self.skip_block_to_end(p)
                return None
            if kw == "do":
                p.next(); r = self.block(p, env, stop=()); p.expect("kw", "end"); return r
            raise LuaError("unsupported keyword %s" % kw)
        # assignment or call
        start = p.i
        target = self.lvalue_or_expr(p, env)
        return None

    def skip_branch(self, p):
        depth = 0
        while True:
            k, v = p.peek()
            if k == "eof":
                raise LuaError("eof")
            if depth == 0 and k == "kw" and v in ("else", "elseif", "end"):
                return
            p.next()
            if k == "kw" and v in ("function", "if", "do", "repeat"):
                depth += 1
            elif k == "kw" and v in ("end", "until"):
                depth -= 1

    def exprlist(self, p, env):
        vals = [p.expr()]
        while p.accept("op", ","):
            vals.append(p.expr())
        return vals

    def lvalue_or_expr(self, p, env):
        # parse prefix chain manually: name { .name | [expr] } then '=' or call
        save = p.i
        k, name = p.next()
        if k != "name":
            raise LuaError("statement starts with %r" % ((k, name),))
        container, key = env, name
        while True:
            t = p.peek()
            if t == ("op", "."):
                p.next()
                nxt = p.expect("name")[1]
                container = self.resolve(container, key, env)
                key = nxt
            elif t == ("op", "["):
                p.next()
                kexpr = p.expr()
                p.expect("op", "]")
                container = self.resolve(container, key, env)
                key = kexpr
            else:
                break
        if p.accept("op", "="):
            val = p.expr()
            if container is not None and container is not UNKNOWN and isinstance(container, dict):
                if isinstance(container, ChainEnv):
                    container.assign(key, val)
                else:
                    container[key] = val
            return None
        # function call statement: rewind and parse as expression; ignore result
        p.i = save
        try:
            p.expr()
        except LuaError as e:
            self.warnings.append(str(e))
            # skip to next line-ish: give up on rest of statement
        return None

    def resolve(self, container, key, env):
        if container is UNKNOWN or container is None:
            return UNKNOWN
        if container is env:
            v = env.get(key, UNKNOWN) if not isinstance(env, ChainEnv) else env.lookup(key)
        else:
            v = container.get(key, UNKNOWN) if isinstance(container, dict) else UNKNOWN
        return v


class ChainEnv(dict):
    """Local scope chained to a parent mapping."""
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
    def set_local(self, k, v):
        dict.__setitem__(self, k, v)
    def lookup(self, k):
        if dict.__contains__(self, k):
            return dict.__getitem__(self, k)
        if isinstance(self.parent, ChainEnv):
            return self.parent.lookup(k)
        return self.parent.get(k, UNKNOWN)
    def assign(self, k, v):
        if dict.__contains__(self, k):
            dict.__setitem__(self, k, v)
        elif isinstance(self.parent, ChainEnv):
            self.parent.assign(k, v)
        else:
            self.parent[k] = v
    def __contains__(self, k):
        return self.lookup(k) is not UNKNOWN
    def __getitem__(self, k):
        v = self.lookup(k)
        if v is UNKNOWN:
            raise KeyError(k)
        return v
    def get(self, k, d=None):
        v = self.lookup(k)
        return d if v is UNKNOWN else v
