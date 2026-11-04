#!/usr/bin/env python3
"""Build a slim quest-giver dataset for WoW Forever from Questie/QuestieDB (GPL-3.0) sources.
Parses the Lua data as text; executes nothing from the repositories."""
import re, sys, json, os
sys.path.insert(0, os.path.dirname(__file__))
from luaparse import tokenize, Parser, eval_expr, LuaTable, seq, LuaError, UNKNOWN
from luaexec import Interp

HERE = os.path.dirname(os.path.abspath(__file__))
QDB = os.environ.get("QUESTIEDB", os.path.join(HERE, "..", "vendor", "QuestieDB"))
QST = os.environ.get("QUESTIE", os.path.join(HERE, "..", "vendor", "Questie"))
OUT = os.path.join(HERE, "..", "QuestGiverPins", "Data.lua")

def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()

def strip_varargs(src):
    return re.sub(r"local\s+[\w\s,]+=\s*\.\.\.\s*\n", "\n", src)

# ---------------- enums ----------------
constants = LuaTable()
genv = {"LibQuestieDB": LuaTable({"Enum": constants})}
cfg = read(f"{QDB}/src/config.lua")
enum_files = re.findall(r'"(src/corrections/enum/[^"]+)"', cfg.split("config.enumFiles", 1)[1].split("}", 1)[0])
for f in enum_files[1:]:
    it = Interp(genv)
    it.env["constants"] = constants
    it.run_file(strip_varargs(read(f"{QDB}/{f}")).replace("local constants = LibQuestieDB.Enum", ""))
    for w in it.warnings:
        print("enum warn", f, w[:120])
print("enum tables:", sorted(constants.keys()))

fe = constants["byExpansion"]["Forever"]
classic = constants["byExpansion"]["Classic"]

# ---------------- meta keys ----------------
def meta_keys(entity):
    src = read(f"{QDB}/src/meta/{entity}Meta.lua")
    body = src.split("keys = {", 1)[1].split("\n  },", 1)[0]
    return {k: int(v) for k, v in re.findall(r"\['(\w+)'\]\s*=\s*(\d+)", body)}
QK, NK, OK = meta_keys("quest"), meta_keys("npc"), meta_keys("object")
QSTRUCT = dict(re.findall(r"\[(\d+)\]='(\w+)'", read(f"{QDB}/src/meta/questMeta.lua").split("structures = {", 1)[1].split("}", 1)[0]))

class KeyNS(LuaTable):
    """questKeys.foo -> 'foo' (symbolic)."""
    def missing(self, k):
        return k

def mod(**kw):
    return LuaTable(kw)

modules = {
    "QuestieDB": mod(questKeys=KeyNS(), npcKeys=KeyNS(), objectKeys=KeyNS(), itemKeys=KeyNS(),
                     raceKeys=fe["raceKeys"], classKeys=classic["classKeys"], npcFlags=fe["npcFlags"],
                     sortKeys=constants["sortKeys"], specialFlags=constants["specialFlags"],
                     questFlags=constants["questFlags"], factionIDs=constants["factionIDs"],
                     waypointPresets=constants.get("waypointPresets", LuaTable())),
    "ZoneDB": mod(zoneIDs=constants["zoneIDs"]),
    "QuestieProfessions": mod(professionKeys=constants["professionKeys"],
                              specializationKeys=constants["specializationKeys"], rankNames=constants["rankNames"]),
    "Phasing": mod(phases=constants["phases"]),
    "QuestieCorrections": LuaTable(),
    "l10n": (lambda *a: a[0] if a else None),
}
def import_module(_self, name):
    return modules.get(name, LuaTable())
def create_module(_self, name):
    t = LuaTable(); modules[name] = t; return t
QuestieLoader = LuaTable({"ImportModule": import_module, "CreateModule": create_module})

def run_correction(path, method="Load"):
    env = {"QuestieLoader": QuestieLoader, "UnitFactionGroup": lambda *a: None,
           "UnitClassBase": lambda *a: None, "UnitRace": lambda *a: None}
    it = Interp(env)
    it.run_file(read(path))
    fname = [k for k in it.functions if k.endswith(":" + method) or k.endswith("." + method)]
    if not fname:
        raise SystemExit(f"no {method} in {path}: {list(it.functions)}")
    r = it.call(fname[0])
    for w in it.warnings[:5]:
        print("  warn", os.path.basename(path), w[:150])
    if it.unknowns:
        print("  unknown ids", os.path.basename(path), dict(list(it.unknowns.items())[:8]))
    return r[1] if r else None

# ---------------- base data ----------------
def load_base(path, var):
    src = read(path)
    m = re.search(var + r"\s*=\s*\[\[return\s*", src)
    body = src[m.end():]
    body = body[: body.rindex("}]]") + 1]
    print("parsing", os.path.basename(path), len(body) // 1024, "KB")
    t = eval_expr(body)
    return {k: {i + 1: v for i, v in enumerate(seq(row)) if v is not None} for k, row in t.items()}

quests = load_base(f"{QDB}/data/Forever/foreverQuestDB.lua", "QuestieDB.questData")
npcs = load_base(f"{QDB}/data/Forever/foreverNpcDB.lua", "QuestieDB.npcData")
objects = load_base(f"{QDB}/data/Forever/foreverObjectDB.lua", "QuestieDB.objectData")
print("base:", len(quests), "quests", len(npcs), "npcs", len(objects), "objects")

# ---------------- merge corrections ----------------
def norm(v):
    """canonical comparable form"""
    if isinstance(v, dict):
        return tuple(sorted((k, norm(x)) for k, x in v.items()))
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v

def list_add(existing, operand):
    out = list(seq(existing)) if existing else []
    out = [x for x in out if x is not None]
    have = {norm(x) for x in out}
    for x in seq(operand):
        if x is not None and norm(x) not in have:
            out.append(x); have.add(norm(x))
    return LuaTable({i + 1: x for i, x in enumerate(out)})

def list_remove(existing, operand):
    if not existing:
        return existing
    rm = {norm(x) for x in seq(operand) if x is not None}
    out = [x for x in seq(existing) if x is not None and norm(x) not in rm]
    return LuaTable({i + 1: x for i, x in enumerate(out)})

def grouped(existing, operand, fn, inner_is_list=True):
    out = LuaTable(existing or {})
    for g, val in operand.items():
        out[g] = fn(out.get(g), val)
        if not out[g]:
            del out[g]
    return out

def apply_op(shape, existing, operand, op):
    f = list_add if op == "add" else list_remove
    if shape in ("questgivers", "spawnlist", "waypointlist", "objectives_groups"):
        return grouped(existing, operand, f)
    if shape in ("pair", "trigger"):
        return operand if op == "add" else None
    return f(existing, operand)

NPC_SHAPES = {"spawns": "spawnlist", "waypoints": "waypointlist", "questStarts": "idarray", "questEnds": "idarray"}
OBJ_SHAPES = {"spawns": "spawnlist", "questStarts": "idarray", "questEnds": "idarray"}
Q_SHAPES = {name: QSTRUCT.get(str(idx), "scalar") for name, idx in QK.items()}

def merge(db, keys, shapes, corr, label, options=None):
    if not corr:
        return
    created = changed = 0
    for eid, row in corr.items():
        if not isinstance(row, dict):
            continue
        if eid not in db:
            if options and options.get("noNewEntries"):
                continue
            db[eid] = {}; created += 1
        ent = db[eid]
        for fkey, val in row.items():
            if not isinstance(fkey, str):
                continue
            op = None
            name = fkey
            if fkey.endswith("_add"):
                op, name = "add", fkey[:-4]
            elif fkey.endswith("_remove"):
                op, name = "remove", fkey[:-7]
            if name not in keys:
                continue
            idx = keys[name]
            if op:
                if isinstance(val, dict) and not val:
                    continue
                newv = apply_op(shapes.get(name, "idarray"), ent.get(idx), val, op)
                if newv:
                    ent[idx] = newv
                else:
                    ent.pop(idx, None)
            else:
                if options and options.get("noOverwrites") and idx in ent:
                    continue
                if isinstance(val, dict) and not val:
                    ent.pop(idx, None)
                else:
                    ent[idx] = val
            changed += 1
    print(f"  {label}: {len(corr)} rows, {created} new, {changed} field writes")

C = f"{QDB}/src/corrections/Forever"
order = re.findall(r"file = 'Forever/([^']+)',\s*module = '(\w+)',\s*datatype = '(\w+)',\s*static = \{'(\w+)'\}(?:,\s*dynamic = \{[^}]*\})?(?:,\s*options = (\{[^}]*\}))?", cfg)
targets = {"Quest": (quests, QK, Q_SHAPES), "Npc": (npcs, NK, NPC_SHAPES), "Object": (objects, OK, OBJ_SHAPES)}
for f, modname, dtype, method, opts in order:
    if dtype not in targets:
        continue
    options = {"noNewEntries": "noNewEntries" in (opts or ""), "noOverwrites": "noOverwrites" in (opts or "")}
    corr = run_correction(f"{C}/{f}", method)
    db, keys, shapes = targets[dtype]
    merge(db, keys, shapes, corr, f, options)
print("merged:", len(quests), "quests", len(npcs), "npcs", len(objects), "objects")

# ---------------- blacklist (Questie, Era rules since Forever == Era there) ----------------
bl_src = read(f"{QST}/Database/Corrections/QuestieQuestBlacklist.lua")
Exp = LuaTable({"Era": 1, "Tbc": 2, "Wotlk": 3, "Cata": 4, "MoP": 5, "Current": 1})
QuestieG = LuaTable({"IsForever": True, "IsClassic": True, "IsChinaRegion": False, "IsTitanReforged": False,
                     "Debug": lambda *a: None, "DEBUG_DEVELOP": 1})
ContentPhases = LuaTable({"activePhases": LuaTable({"SoM": 5, "SoD": 7, "Anniversary": 6, "MoP": 5, "TBC": 4})})
modules.update({"Expansions": Exp, "ContentPhases": ContentPhases})
benv = {"QuestieLoader": QuestieLoader, "Questie": QuestieG}
it = Interp(benv)
it.run_file(bl_src)
blacklist = it.call("QuestieQuestBlacklist:Load")[1]
hidden = {int(q) for q, v in blacklist.items() if v not in (None, False)}
qbl = modules["QuestieQuestBlacklist"]
for extra in ("InvasionQuests", "AQWarEffortQuests"):
    for q, v in (qbl.get(extra) or {}).items():
        if v:
            hidden.add(int(q))
print("blacklisted quests:", len(hidden))

# ---------------- zones ----------------
def load_zone_map(path, var):
    src = read(path)
    m = re.search(r"ZoneDB\.private\." + var + r"\s*=\s*\[\[return\s*", src)
    body = src[m.end():]
    body = body[: body.index("}]]") + 1]
    return dict(eval_expr(body))
Z = f"{QDB}/support/Forever/Zones"
a2u = load_zone_map(f"{Z}/areaIdToUiMapId.lua", "areaIdToUiMapId")
a2u.update(load_zone_map(f"{Z}/areaIdToUiMapId.lua", "areaIdToUiMapIdOverride"))
sub2p = load_zone_map(f"{Z}/subZoneToParentZone.lua", "subZoneToParentZone")
sub2p.update(load_zone_map(f"{Z}/subZoneToParentZone.lua", "subZoneToParentZoneOverride"))

def ui_map(area):
    seen = set()
    while area is not None and area not in seen:
        seen.add(area)
        u = a2u.get(area)
        if u:
            return u
        area = sub2p.get(area)
    return None

# ---------------- build output ----------------
holiday = set()
sk = constants["sortKeys"]
for name in ("WINTER_VEIL", "HARVEST_FESTIVAL", "CHILDRENS_WEEK", "LOVE_IS_IN_THE_AIR", "PILGRIMS_BOUNTY", "NOBLEGARDEN",
             "BREWFEST", "MIDSUMMER", "LUNAR_FESTIVAL", "DARKMOON_FAIRE", "DAY_OF_THE_DEAD", "SEASONAL", "HALLOWS_END"):
    if name in sk:
        holiday.add(sk[name])

def ids(v):
    return [int(x) for x in seq(v) if isinstance(x, (int, float))] if isinstance(v, dict) else []

def pair(v):
    s = seq(v) if isinstance(v, dict) else []
    return [s[0], s[1]] if len(s) >= 2 and s[0] is not None else None

# givers: key ("n"/"o", id) -> set(questIds)
giver_quests = {}
qout = {}
skipped = {"hidden": 0, "noname": 0, "nogiver": 0}
for qid, q in quests.items():
    if qid in hidden:
        skipped["hidden"] += 1; continue
    name = q.get(QK["name"])
    if not isinstance(name, str):
        skipped["noname"] += 1; continue
    sb = q.get(QK["startedBy"]) or {}
    starters = [("n", n) for n in ids(sb.get(1))] + [("o", o) for o in ids(sb.get(2))]
    if not starters:
        skipped["nogiver"] += 1; continue
    for s in starters:
        giver_quests.setdefault(s, set()).add(qid)
    g = lambda k: q.get(QK[k])
    flags = int(g("questFlags") or 0)
    special = int(g("specialFlags") or 0)
    zos = int(g("zoneOrSort") or 0)
    qout[qid] = {
        "n": name, "rl": int(g("requiredLevel") or 0), "ql": int(g("questLevel") or 0),
        "ra": int(g("requiredRaces") or 0), "cl": int(g("requiredClasses") or 0),
        "pg": ids(g("preQuestGroup")), "ps": ids(g("preQuestSingle")), "ex": ids(g("exclusiveTo")),
        "nx": int(g("nextQuestInChain") or 0), "pa": int(g("parentQuest") or 0),
        "bf": int(g("breadcrumbForQuestId") or 0), "bc": ids(g("breadcrumbs")),
        "sk": pair(g("requiredSkill")), "mi": pair(g("requiredMinRep")), "ma": pair(g("requiredMaxRep")),
        "sp": int(g("requiredSpell") or 0), "ml": int(g("requiredMaxLevel") or 0),
        "uc": int(g("availableUntilCompleted") or 0), "sw": int(g("availableStartingWith") or 0),
        "db": int(g("disabledByQuest") or 0),
        "rep": 1 if (special & 1) else 0, "day": 1 if (flags & (4096 | 32768)) else 0,
        "ev": 1 if zos in holiday else 0,
    }
# drop pre-quest refs to quests that don't exist so they can't block forever
for q in qout.values():
    q["pg"] = [x for x in q["pg"] if abs(x) in quests]
    q["ps"] = [x for x in q["ps"] if x in quests]

givers = []
by_map = {}
nospawn = 0
for (kind, gid), qset in sorted(giver_quests.items()):
    src = npcs if kind == "n" else objects
    keys = NK if kind == "n" else OK
    ent = src.get(gid)
    if not ent:
        nospawn += 1; continue
    spawns = ent.get(keys["spawns"]) or {}
    pts = []
    for area, coords in spawns.items():
        u = ui_map(area)
        if not u:
            continue
        for c in seq(coords):
            s = seq(c) if isinstance(c, dict) else []
            if len(s) >= 2 and isinstance(s[0], (int, float)) and s[0] >= 0 and s[1] >= 0:
                pts.append((u, round(s[0] / 100, 4), round(s[1] / 100, 4)))
    if not pts:
        nospawn += 1; continue
    # dedupe near-identical points per map
    seen = set(); upts = []
    for p in pts:
        k = (p[0], round(p[1], 3), round(p[2], 3))
        if k not in seen:
            seen.add(k); upts.append(p)
    name = ent.get(keys["name"]) or "?"
    fr = ent.get(NK["friendlyToFaction"]) if kind == "n" else None
    idx = len(givers) + 1
    givers.append((name, kind, fr, sorted(qset)))
    for u, x, y in upts:
        if u in (947, 1414, 1415):
            continue
        by_map.setdefault(u, []).extend([idx, x, y])

print("skipped quests:", skipped, "givers without usable spawns:", nospawn)
print("givers:", len(givers), "maps:", len(by_map), "pins:", sum(len(v) // 3 for v in by_map.values()))

# ---------------- write Lua ----------------
def lstr(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
def larr(a):
    return "{" + ",".join(str(x) for x in a) + "}"
def lnum(x):
    if isinstance(x, float):
        return ("%.4f" % x).rstrip("0").rstrip(".")
    return str(x)

out = []
out.append("-- Generated quest-giver data for WoW Forever.")
out.append("-- Derived from QuestieDB (https://github.com/Questie/QuestieDB) and Questie's quest blacklist, GPL-3.0.")
out.append("local _, ns = ...")
out.append("-- quests[id] = {name, reqLevel, questLevel, races, classes, preGroup, preSingle, exclusiveTo, nextInChain,")
out.append("--   parentQuest, breadcrumbFor, breadcrumbs, reqSkill, minRep, maxRep, reqSpell, maxLevel, untilCompleted,")
out.append("--   startingWith, disabledBy, repeatable, daily, event}")
out.append("ns.quests = {")
for qid in sorted(qout):
    q = qout[qid]
    def opt(v):
        return "nil" if not v else (larr(v) if isinstance(v, list) else lnum(v))
    fields = [lstr(q["n"]), lnum(q["rl"]), lnum(q["ql"]), lnum(q["ra"]), lnum(q["cl"]), opt(q["pg"]), opt(q["ps"]),
              opt(q["ex"]), opt(q["nx"]), opt(q["pa"]), opt(q["bf"]), opt(q["bc"]),
              opt(q["sk"]), opt(q["mi"]), opt(q["ma"]), opt(q["sp"]), opt(q["ml"]), opt(q["uc"]), opt(q["sw"]),
              opt(q["db"]), opt(q["rep"]), opt(q["day"]), opt(q["ev"])]
    while fields and fields[-1] == "nil":
        fields.pop()
    out.append("[%d]={%s}," % (qid, ",".join(fields)))
out.append("}")
out.append("-- givers[i] = {name, kind ('n' npc / 'o' object), friendlyTo ('A','H','AH' or nil), {questIds}}")
out.append("ns.givers = {")
for name, kind, fr, ql in givers:
    out.append("{%s,%s,%s,%s}," % (lstr(name), lstr(kind), lstr(fr) if isinstance(fr, str) else "nil", larr(ql)))
out.append("}")
out.append("-- pins[uiMapId] = {giverIndex, x, y, giverIndex, x, y, ...}  (x/y are 0-1 map fractions)")
out.append("ns.pins = {")
for u in sorted(by_map):
    v = by_map[u]
    out.append("[%d]={%s}," % (u, ",".join(lnum(x) for x in v)))
out.append("}")
with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("wrote", OUT, os.path.getsize(OUT) // 1024, "KB")
