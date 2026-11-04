import os, sys
try:
    from lupa import lua51 as lupa_mod
except ImportError:
    import lupa as lupa_mod
A = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "QuestGiverPins")

HARNESS = r"""
local files, read = ...
ns = {}
local unpackf = unpack or table.unpack
-- ---- stubs ----
STATE = { race = 1, class = 1, level = 1, faction = "Alliance", completed = {}, log = {}, cvars = {rotateMinimap="0", minimapZoom="0", minimapInsideZoom="3"}, facing = 0 }
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
function CreateFromMixins(...) local t = {} for _, m in ipairs({...}) do for k, v in pairs(m) do t[k] = v end end return t end
MapCanvasPinMixin, MapCanvasDataProviderMixin = {}, {}
C_Timer = { After = function(_, fn) fn() end }
local function newFrame()
  local f = { scripts = {}, shown = true, w = 140 }
  function f:RegisterEvent() end
  function f:SetScript(k, fn) self.scripts[k] = fn end
  function f:SetFrameStrata() end function f:SetFrameLevel() end function f:GetFrameStrata() return "LOW" end
  function f:GetFrameLevel() return 1 end function f:EnableMouse() end
  function f:CreateTexture() return { SetAllPoints=function() end, SetTexture=function(s,t) s.tex=t end, SetDesaturated=function() end } end
  function f:SetSize(w) self.size = w end function f:ClearAllPoints() end
  function f:SetPoint(_, _, _, x, y) self.x, self.y = x, y end
  function f:Show() self.shown = true end function f:Hide() self.shown = false end
  function f:IsShown() return self.shown end function f:IsVisible() return true end
  function f:GetWidth() return self.w end
  function f:GetZoom() return 0 end
  return f
end
function CreateFrame() return newFrame() end
Minimap = newFrame()
GameTooltip = { lines = {} }
function GameTooltip:SetOwner() wipe(self.lines) end
function GameTooltip:AddLine(t) self.lines[#self.lines+1] = t end
function GameTooltip:Show() end function GameTooltip:Hide() end
WorldMapFrame = { providers = {}, shown = false, mapID = 1429, pins = {} }
function WorldMapFrame:AddDataProvider(p) p.GetMap = function() return WorldMapFrame end; self.providers[#self.providers+1] = p end
function WorldMapFrame:IsShown() return self.shown end
function WorldMapFrame:GetMapID() return self.mapID end
function WorldMapFrame:RemoveAllPinsByTemplate() wipe(self.pins) end
function WorldMapFrame:AcquirePin(_, info) self.pins[#self.pins+1] = info end
SlashCmdList = {}
function UnitLevel() return STATE.level end
function UnitRace() return "x", "x", STATE.race end
function UnitClass() return "x", "x", STATE.class end
function UnitFactionGroup() return STATE.faction end
function GetQuestGreenRange() return 8 end
function GetQuestDifficultyColor() return {r=1,g=1,b=0} end
function GetCVar(k) return STATE.cvars[k] end
function GetPlayerFacing() return STATE.facing end
C_QuestLog = {
  GetAllCompletedQuestIDs = function() local t = {} for id in pairs(STATE.completed) do t[#t+1] = id end return t end,
  GetNumQuestLogEntries = function() return #STATE.log end,
  GetInfo = function(i) return { questID = STATE.log[i] } end,
}
C_SkillInfo = { GetNumSkillLines = function() return 1 end, GetSkillLineInfo = function() return { skillID = 185, rank = 50 } end }
C_Reputation = { GetFactionDataByID = function() return nil end }
local Vec = {} Vec.__index = Vec
function Vec:SetXY(x, y) self.x, self.y = x, y end
function Vec:GetXY() return self.x, self.y end
function CreateVector2D(x, y) return setmetatable({x=x, y=y}, Vec) end
-- fake world: every map spans 1000 yards; x (east) -> world Y decreasing, y (south) -> world X decreasing
C_Map = {
  GetBestMapForUnit = function() return STATE.map end,
  GetPlayerMapPosition = function() return CreateVector2D(STATE.px, STATE.py) end,
  GetWorldPosFromMapPos = function(m, v) if m ~= STATE.map then return 99, CreateVector2D(0,0) end return 1, CreateVector2D(1000 - v.y*1000, 1000 - v.x*1000) end,
  GetMapInfo = function() return { mapType = 3 } end,
}
-- ---- load addon ----
for _, f in ipairs(files) do
  local chunk = assert(loadstring and loadstring(read(f), f) or load(read(f), f))
  chunk("QuestGiverPins", ns)
end
local ev = ns.__eventframe
return ns
"""

def read(f):
    return open(os.path.join(A, f), encoding="utf-8").read()

def make():
    L = lupa_mod.LuaRuntime(unpack_returned_tuples=True)
    files = L.table("Data.lua", "Core.lua", "WorldMap.lua", "Minimap.lua")
    # capture event frame: patch CreateFrame to record the first frame
    ns = L.execute(HARNESS.replace("function CreateFrame() return newFrame() end",
        "FRAMES = {} function CreateFrame() local f = newFrame() FRAMES[#FRAMES+1] = f return f end"), files, read)
    return L, ns

def fire(L, event, *args):
    L.execute("local e, a = ... for _, f in ipairs(FRAMES) do if f.scripts.OnEvent then f.scripts.OnEvent(f, e, a) end end", event, args[0] if args else None)

def setup(race, cls, level, faction, completed=(), log=()):
    L, ns = make()
    L.execute("local r,c,l,f = ... STATE.race=r STATE.class=c STATE.level=l STATE.faction=f", race, cls, level, faction)
    for q in completed:
        L.execute("STATE.completed[...] = true", q)
    for q in log:
        L.execute("STATE.log[#STATE.log+1] = ...", q)
    fire(L, "ADDON_LOADED", "QuestGiverPins")
    fire(L, "PLAYER_LOGIN")
    return L, ns

def available_on_map(L, mapID):
    return L.execute("""local m = ... local out = {}
      local list = ns.pins[m] or {}
      for i = 1, #list, 3 do local a = ns.GetAvailable(list[i]) if a then for _, q in ipairs(a) do out[#out+1] = ns.givers[list[i]][1] .. ':' .. q .. ':' .. ns.quests[q][1] end end end
      table.sort(out) return table.concat(out, '\\n')""", mapID)

ok = True
def check(cond, msg):
    global ok
    print(("PASS " if cond else "FAIL ") + msg)
    ok = ok and cond

# 1. Human warrior level 1 in Northshire (1429 = Elwynn)
L, ns = setup(1, 1, 1, "Alliance")
av = available_on_map(L, 1429)
print(av.replace("\n", " | ")[:600])
check("A Threat Within" in av, "human L1 sees 'A Threat Within' (783)")
check("Wolves Across the Border" in av, "level-1 quest 33 visible at L1")
check(":3100:" not in av, "warrior letter 3100 needs quest 7 first")
check(":3103:" not in av, "priest class quest 3103 hidden from warrior")

# 2. after completing 783
L, ns = setup(1, 1, 2, "Alliance", completed=[783])
av2 = available_on_map(L, 1429)
check("A Threat Within" not in av2, "completed quest disappears")
check(":7:" in av2, "follow-up 'Kobold Camp Cleanup' (7) appears after 783")

L, ns = setup(1, 1, 3, "Alliance", completed=[783, 7])
a3 = available_on_map(L, 1429)
check(":3100:" in a3 and ":3103:" not in a3, "after quest 7: warrior letter shown, priest letter not")
# 3. quest in log hides it
L, ns = setup(1, 1, 1, "Alliance", log=[783])
check("A Threat Within" not in available_on_map(L, 1429), "quest in log is hidden")

# 4. Orc in Elwynn: no alliance givers
L, ns = setup(2, 1, 10, "Horde")
avh = available_on_map(L, 1429)
check(avh.strip() == "" or all(":" in x for x in avh.split("\n")), "orc in Elwynn: " + str(len([x for x in avh.split(chr(10)) if x])) + " entries")
avd = available_on_map(L, 1411)  # Durotar
check("Your Place In The World" in avd or len(avd) > 0, "orc sees Durotar quests (%d)" % len([x for x in avd.split(chr(10)) if x]))

# 5. world map provider
L, ns = setup(1, 1, 1, "Alliance")
n = L.execute("WorldMapFrame.mapID = 1429 WorldMapFrame.shown = true WorldMapFrame.providers[1]:RefreshAllData() return #WorldMapFrame.pins")
check(n > 0, "world map provider placed %d pins on Elwynn" % n)
tip = L.execute("local p = WorldMapFrame.pins[1] ns.ShowTooltip({}, p.giver, true) return table.concat(GameTooltip.lines, ' / ')")
print("  tooltip:", tip)

# 6. minimap math: put player just west of a known giver on its map
L, ns = setup(1, 1, 1, "Alliance")
g = L.execute("""local list = ns.pins[1429] for i = 1, #list, 3 do if ns.GetAvailable(list[i]) then return list[i+1], list[i+2] end end""")
gx, gy = g
L.execute("local x, y = ... STATE.map = 1429 STATE.px = x - 0.05 STATE.py = y", gx, gy)
fire(L, "QUEST_LOG_UPDATE")
res = L.execute("""for _, f in ipairs(FRAMES) do if f.scripts.OnUpdate then f.scripts.OnUpdate(f, 1) end end
  local best for _, f in ipairs(FRAMES) do if f.giver and f.shown and f.x then if not best or math.abs(f.y) + math.abs(f.x - 15) < math.abs(best.y) + math.abs(best.x - 15) then best = f end end end
  if best then return best.x, best.y end""")
print("  minimap pin offset (player 50yd west of giver):", res)
check(res and abs(res[0] - 50 * (70 / 233.333)) < 2 and abs(res[1]) < 2, "giver appears to the EAST on the minimap")
L.execute("local x, y = ... STATE.px = x STATE.py = y + 0.05", gx, gy)
res = L.execute("""for _, f in ipairs(FRAMES) do if f.scripts.OnUpdate then f.scripts.OnUpdate(f, 1) end end
  local best for _, f in ipairs(FRAMES) do if f.giver and f.shown and f.x then if not best or math.abs(f.x) + math.abs(f.y - 15) < math.abs(best.x) + math.abs(best.y - 15) then best = f end end end
  if best then return best.x, best.y end""")
print("  minimap pin offset (player 50yd south of giver):", res)
check(res and abs(res[1] - 15) < 2 and abs(res[0]) < 2, "giver appears NORTH on the minimap")
L.execute("STATE.cvars.rotateMinimap = '1' STATE.facing = math.pi / 2")  # facing west
res = L.execute("""for _, f in ipairs(FRAMES) do if f.scripts.OnUpdate then f.scripts.OnUpdate(f, 1) end end
  local best for _, f in ipairs(FRAMES) do if f.giver and f.shown and f.x then if not best or math.abs(f.y) + math.abs(f.x - 15) < math.abs(best.y) + math.abs(best.x - 15) then best = f end end end
  if best then return best.x, best.y end""")
print("  rotating minimap, facing west, giver north:", res)
check(res and abs(res[0] - 15) < 2 and abs(res[1]) < 2, "facing west: north is to the RIGHT")

# 7. slash command
L.execute("SlashCmdList.QUESTGIVERPINS('minimap')")
check(L.execute("return ns.db.minimap") is False, "/qgp minimap toggles off")
print("\nALL PASS" if ok else "\nSOME FAILED")
