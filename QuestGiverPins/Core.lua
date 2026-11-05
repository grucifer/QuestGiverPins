-- Quest Giver Pins: availability logic, settings and slash command.
local ADDON, ns = ...

local floor, pairs, ipairs, wipe, tostring = math.floor, pairs, ipairs, wipe, tostring

ns.ICON_AVAILABLE = "Interface\\GossipFrame\\AvailableQuestIcon"
ns.ICON_REPEATABLE = "Interface\\GossipFrame\\DailyQuestIcon"

local defaults = {
    worldMap = true,     -- pins on zone maps
    continent = false,   -- also draw pins on continent maps
    minimap = true,      -- pins on the minimap
    lowLevel = false,    -- show quests that are gray (trivial) for you
    events = false,      -- show holiday/event quests
    repeatable = true,   -- show repeatable and daily quests
    mapScale = 1.0,
    minimapScale = 1.0,
}

-- Quest record field positions (see Data.lua header)
local NAME, REQLEVEL, QLEVEL, RACES, CLASSES, PREGROUP, PRESINGLE, EXCLUSIVE, NEXTCHAIN,
      PARENT, BREADCRUMBFOR, BREADCRUMBS, SKILL, MINREP, MAXREP, SPELL, MAXLEVEL,
      UNTILDONE, STARTWITH, DISABLEDBY, REPEATABLE, DAILY, EVENT = 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23
ns.Q = { NAME = NAME, REQLEVEL = REQLEVEL, QLEVEL = QLEVEL, REPEATABLE = REPEATABLE, DAILY = DAILY }

-- Race ID -> requiredRaces bit (Forever's Skyborne races use bits 32/33, beyond 32-bit bit ops)
local raceBitById = {
    [1] = 1, [2] = 2, [3] = 4, [4] = 8, [5] = 16, [6] = 32, [7] = 64, [8] = 128, [9] = 256,
    [10] = 512, [11] = 1024, [22] = 2097152, [24] = 8388608, [25] = 16777216, [26] = 33554432,
    [95] = 4294967296, [96] = 8589934592,
}

local function HasBit(mask, bitValue)
    return floor(mask / bitValue) % 2 == 1
end

---------------------------------------------------------------------------
-- Player state
---------------------------------------------------------------------------
local completed, inLog, skills, repCache = {}, {}, {}, {}
-- quests turned in this session: the server's completed list can lag behind QUEST_TURNED_IN,
-- so these are kept and merged back in every time that list is re-read
local turnedIn = {}
local player = { level = 1, raceBit = 0, classBit = 0, faction = "A" }

local function RefreshCompleted()
    wipe(completed)
    local list
    if C_QuestLog and C_QuestLog.GetAllCompletedQuestIDs then
        list = C_QuestLog.GetAllCompletedQuestIDs()
        if list then
            for _, id in ipairs(list) do completed[id] = true end
        end
    elseif GetQuestsCompleted then
        GetQuestsCompleted(completed)
    end
    for id in pairs(turnedIn) do completed[id] = true end
end

local function RefreshQuestLog()
    wipe(inLog)
    if C_QuestLog and C_QuestLog.GetNumQuestLogEntries then
        for i = 1, C_QuestLog.GetNumQuestLogEntries() do
            local info = C_QuestLog.GetInfo(i)
            if info and not info.isHeader and info.questID and info.questID > 0 then
                inLog[info.questID] = true
            end
        end
    elseif GetNumQuestLogEntries then
        for i = 1, GetNumQuestLogEntries() do
            local _, _, _, isHeader, _, _, _, questID = GetQuestLogTitle(i)
            if not isHeader and questID then inLog[questID] = true end
        end
    end
end

local function RefreshSkills()
    wipe(skills)
    if C_SkillInfo and C_SkillInfo.GetNumSkillLines then
        -- Expand collapsed headers back to front so indices stay valid.
        if C_SkillInfo.ExpandSkillHeader then
            for i = C_SkillInfo.GetNumSkillLines(), 1, -1 do
                local s = C_SkillInfo.GetSkillLineInfo(i)
                if s and s.isHeader and s.isCollapsed then C_SkillInfo.ExpandSkillHeader(i) end
            end
        end
        for i = 1, C_SkillInfo.GetNumSkillLines() do
            local s = C_SkillInfo.GetSkillLineInfo(i)
            if s and not s.isHeader and s.skillID then skills[s.skillID] = s.rank or 0 end
        end
    elseif GetProfessions and GetProfessionInfo then
        for _, idx in pairs({ GetProfessions() }) do
            if idx then
                local _, _, rank, _, _, _, skillLine = GetProfessionInfo(idx)
                if skillLine then skills[skillLine] = rank or 0 end
            end
        end
    end
end

local function GetRep(factionID)
    local v = repCache[factionID]
    if v ~= nil then return v end
    v = 0
    if C_Reputation and C_Reputation.GetFactionDataByID then
        local d = C_Reputation.GetFactionDataByID(factionID)
        if d and d.currentStanding then v = d.currentStanding end
    elseif GetFactionInfoByID then
        local _, _, _, _, _, barValue = GetFactionInfoByID(factionID)
        if barValue then v = barValue end
    end
    repCache[factionID] = v
    return v
end

local function KnowsSpell(id)
    if C_SpellBook and C_SpellBook.IsSpellKnown then
        if C_SpellBook.IsSpellKnown(id) then return true end
    end
    if IsPlayerSpell and IsPlayerSpell(id) then return true end
    if IsSpellKnown and IsSpellKnown(id) then return true end
    return false
end

local function RefreshPlayer()
    player.level = UnitLevel("player") or 1
    local _, _, raceID = UnitRace("player")
    player.raceBit = raceBitById[raceID or 0] or 0
    local _, _, classID = UnitClass("player")
    player.classBit = classID and 2 ^ (classID - 1) or 0
    player.faction = (UnitFactionGroup("player") == "Horde") and "H" or "A"
end

local function TrivialRange()
    if GetQuestGreenRange then return GetQuestGreenRange() end
    if UnitQuestTrivialLevelRange then return UnitQuestTrivialLevelRange("player") end
    return 8
end

function ns.IsTrivial(q)
    local ql = q[QLEVEL] or 0
    if ql <= 0 then return false end
    return ql < player.level - TrivialRange()
end

---------------------------------------------------------------------------
-- Availability (mirrors Questie's QuestieDB.IsDoable for the fields we keep)
---------------------------------------------------------------------------
local function AnyIn(list, set)
    if not list then return false end
    for i = 1, #list do if set[list[i]] then return true end end
    return false
end

local function IsAvailable(questID)
    local q = ns.quests[questID]
    if not q then return false end
    if completed[questID] or inLog[questID] then return false end
    local db = ns.db

    if q[EVENT] and not db.events then return false end
    if (q[REPEATABLE] or q[DAILY]) and not db.repeatable then return false end

    local races = q[RACES]
    if races and races ~= 0 and player.raceBit ~= 0 and not HasBit(races, player.raceBit) then return false end
    local classes = q[CLASSES]
    if classes and classes ~= 0 and player.classBit ~= 0 and not HasBit(classes, player.classBit) then return false end

    if (q[REQLEVEL] or 0) > player.level then return false end
    if q[MAXLEVEL] and q[MAXLEVEL] > 0 and player.level > q[MAXLEVEL] then return false end
    if not db.lowLevel and ns.IsTrivial(q) then return false end

    local preSingle = q[PRESINGLE]
    if preSingle and #preSingle > 0 then
        if not AnyIn(preSingle, completed) then return false end
    else
        local preGroup = q[PREGROUP]
        if preGroup then
            for i = 1, #preGroup do
                local pre = preGroup[i]
                if pre < 0 then
                    if not completed[-pre] then return false end
                elseif not completed[pre] then
                    local pq = ns.quests[pre]
                    if not (pq and AnyIn(pq[EXCLUSIVE], completed)) then return false end
                end
            end
        end
    end

    if q[PARENT] and not inLog[q[PARENT]] then return false end
    local nextQ = q[NEXTCHAIN]
    if nextQ and (completed[nextQ] or inLog[nextQ]) then return false end
    local ex = q[EXCLUSIVE]
    if ex and (AnyIn(ex, completed) or AnyIn(ex, inLog)) then return false end

    local spell = q[SPELL]
    if spell then
        local known = KnowsSpell(spell < 0 and -spell or spell)
        if spell > 0 and not known then return false end
        if spell < 0 and known then return false end
    end

    local bf = q[BREADCRUMBFOR]
    if bf and (completed[bf] or inLog[bf]) then return false end
    if AnyIn(q[BREADCRUMBS], inLog) then return false end
    if q[DISABLEDBY] and inLog[q[DISABLEDBY]] then return false end
    if q[UNTILDONE] and completed[q[UNTILDONE]] then return false end
    local sw = q[STARTWITH]
    if sw and not completed[sw] and not inLog[sw] then return false end

    local skill = q[SKILL]
    if skill then
        local have = skills[skill[1]]
        if not have or have < skill[2] then return false end
    end
    local minRep, maxRep = q[MINREP], q[MAXREP]
    if minRep and GetRep(minRep[1]) < minRep[2] then return false end
    if maxRep and GetRep(maxRep[1]) >= maxRep[2] then return false end

    return true
end
ns.IsAvailable = IsAvailable

-- giverIndex -> array of available quest IDs (false when none); rebuilt lazily
local availableCache = {}
ns.version = 0

function ns.GetAvailable(giverIndex)
    local v = availableCache[giverIndex]
    if v == nil then
        local giver = ns.givers[giverIndex]
        v = false
        local friendly = giver[3]
        if not (friendly and not friendly:find(player.faction, 1, true)) then
            for _, qid in ipairs(giver[4]) do
                if IsAvailable(qid) then
                    v = v or {}
                    v[#v + 1] = qid
                end
            end
        end
        availableCache[giverIndex] = v
    end
    return v or nil
end

-- Callbacks other modules register to redraw when availability changes
ns.listeners = {}
local function NotifyChanged()
    wipe(availableCache)
    ns.version = ns.version + 1
    for _, fn in ipairs(ns.listeners) do fn() end
end
ns.NotifyChanged = NotifyChanged

---------------------------------------------------------------------------
-- Tooltip shared by map and minimap pins
---------------------------------------------------------------------------
function ns.ShowTooltip(owner, giverIndex, showClickHint)
    local giver = ns.givers[giverIndex]
    local avail = ns.GetAvailable(giverIndex)
    if not giver or not avail then return end
    GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
    GameTooltip:AddLine(giver[1], 1, 0.82, 0)
    for _, qid in ipairs(avail) do
        local q = ns.quests[qid]
        local lvl = (q[QLEVEL] and q[QLEVEL] > 0) and q[QLEVEL] or player.level
        local r, g, b = 1, 1, 1
        if GetQuestDifficultyColor then
            local c = GetQuestDifficultyColor(lvl)
            if c then r, g, b = c.r, c.g, c.b end
        end
        local tag = (q[DAILY] and " (Daily)") or (q[REPEATABLE] and " (Repeatable)") or ""
        GameTooltip:AddLine("[" .. lvl .. "] " .. q[NAME] .. tag, r, g, b)
    end
    if showClickHint then
        GameTooltip:AddLine("Click to set a map waypoint", 0.5, 0.5, 0.5)
    end
    GameTooltip:Show()
end

function ns.IconFor(giverIndex)
    local avail = ns.GetAvailable(giverIndex)
    if not avail then return nil end
    local allRepeat, allTrivial = true, true
    for _, qid in ipairs(avail) do
        local q = ns.quests[qid]
        if not (q[REPEATABLE] or q[DAILY]) then allRepeat = false end
        if not ns.IsTrivial(q) then allTrivial = false end
    end
    return allRepeat and ns.ICON_REPEATABLE or ns.ICON_AVAILABLE, allTrivial
end

function ns.SetWaypoint(uiMapID, x, y)
    if not (C_Map and C_Map.CanSetUserWaypointOnMap and C_Map.CanSetUserWaypointOnMap(uiMapID)) then return end
    local point = UiMapPoint and UiMapPoint.CreateFromCoordinates(uiMapID, x, y)
    if not point then return end
    C_Map.SetUserWaypoint(point)
    if C_SuperTrack and C_SuperTrack.SetSuperTrackedUserWaypoint then
        C_SuperTrack.SetSuperTrackedUserWaypoint(true)
    end
end

---------------------------------------------------------------------------
-- Events
---------------------------------------------------------------------------
local pending = false
local function ScheduleRefresh(full)
    if full then ns.needFull = true end
    if pending then return end
    pending = true
    C_Timer.After(0.3, function()
        pending = false
        if ns.needFull then
            ns.needFull = false
            RefreshCompleted()
        end
        RefreshQuestLog()
        RefreshPlayer()
        NotifyChanged()
    end)
end

local f = CreateFrame("Frame")
f:RegisterEvent("ADDON_LOADED")
f:RegisterEvent("PLAYER_LOGIN")
f:RegisterEvent("QUEST_LOG_UPDATE")
f:RegisterEvent("QUEST_ACCEPTED")
f:RegisterEvent("QUEST_TURNED_IN")
f:RegisterEvent("QUEST_REMOVED")
f:RegisterEvent("PLAYER_LEVEL_UP")
f:RegisterEvent("SKILL_LINES_CHANGED")
f:RegisterEvent("UPDATE_FACTION")
f:RegisterEvent("SPELLS_CHANGED")
f:SetScript("OnEvent", function(_, event, arg1)
    if event == "ADDON_LOADED" then
        if arg1 ~= ADDON then return end
        QuestGiverPinsDB = QuestGiverPinsDB or {}
        for k, v in pairs(defaults) do
            if QuestGiverPinsDB[k] == nil then QuestGiverPinsDB[k] = v end
        end
        ns.db = QuestGiverPinsDB
    elseif event == "PLAYER_LOGIN" then
        RefreshPlayer()
        RefreshCompleted()
        RefreshQuestLog()
        RefreshSkills()
        ns.ready = true
        NotifyChanged()
    elseif not ns.ready then
        return
    elseif event == "QUEST_TURNED_IN" then
        if arg1 then
            turnedIn[arg1] = true
            completed[arg1] = true
        end
        inLog[arg1 or 0] = nil
        ScheduleRefresh(true)
    elseif event == "SKILL_LINES_CHANGED" then
        RefreshSkills()
        ScheduleRefresh()
    elseif event == "UPDATE_FACTION" then
        wipe(repCache)
        ScheduleRefresh()
    elseif event == "PLAYER_LEVEL_UP" then
        player.level = arg1 or UnitLevel("player")
        ScheduleRefresh()
    else
        ScheduleRefresh()
    end
end)

---------------------------------------------------------------------------
-- Slash command
---------------------------------------------------------------------------
local toggles = {
    map = { "worldMap", "world map pins" },
    minimap = { "minimap", "minimap pins" },
    continent = { "continent", "pins on continent maps" },
    lowlevel = { "lowLevel", "low-level (gray) quests" },
    events = { "events", "holiday/event quests" },
    repeatable = { "repeatable", "repeatable/daily quests" },
}

local function Print(msg)
    print("|cffffd100Quest Giver Pins:|r " .. msg)
end

SLASH_QUESTGIVERPINS1 = "/qgp"
SLASH_QUESTGIVERPINS2 = "/questgiverpins"
SlashCmdList.QUESTGIVERPINS = function(msg)
    local cmd, arg = (msg or ""):lower():match("^%s*(%S*)%s*(.-)%s*$")
    local t = toggles[cmd]
    if t then
        ns.db[t[1]] = not ns.db[t[1]]
        Print(t[2] .. ": " .. (ns.db[t[1]] and "|cff00ff00on|r" or "|cffff0000off|r"))
        NotifyChanged()
    elseif cmd == "scale" or cmd == "minimapscale" then
        local n = tonumber(arg)
        if n and n >= 0.5 and n <= 3 then
            ns.db[cmd == "scale" and "mapScale" or "minimapScale"] = n
            Print(cmd .. " set to " .. n)
            NotifyChanged()
        else
            Print("usage: /qgp " .. cmd .. " <0.5 - 3>")
        end
    elseif cmd == "reset" then
        for k, v in pairs(defaults) do ns.db[k] = v end
        Print("settings reset")
        NotifyChanged()
    else
        Print("commands:")
        for key, v in pairs(toggles) do
            print(("  /qgp %s  - toggle %s (%s)"):format(key, v[2], ns.db[v[1]] and "on" or "off"))
        end
        print(("  /qgp scale <n>  - world map icon size (%.1f)"):format(ns.db.mapScale))
        print(("  /qgp minimapscale <n>  - minimap icon size (%.1f)"):format(ns.db.minimapScale))
        print("  /qgp reset  - restore defaults")
    end
end
