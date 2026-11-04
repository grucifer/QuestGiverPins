-- Minimap pins. Positions are converted to world yards with C_Map.GetWorldPosFromMapPos,
-- and the east/north axes are measured from the player's current map so no axis
-- convention is assumed.
local _, ns = ...

local sqrt, sin, cos, pairs = math.sqrt, math.sin, math.cos, pairs

-- Minimap diameter in yards per zoom level
local SIZE = {
    indoor = { [0] = 300, 240, 180, 120, 80, 50 },
    outdoor = { [0] = 466 + 2 / 3, 400, 333 + 1 / 3, 266 + 2 / 3, 200, 133 + 1 / 3 },
}

local pool, used = {}, 0
local worldCache = {} -- [zoneID] = { {instance, wx, wy, giver, mapX, mapY}, ... }
local vec = CreateVector2D and CreateVector2D(0, 0)

local function WorldPos(mapID, x, y)
    vec:SetXY(x, y)
    local instance, pos = C_Map.GetWorldPosFromMapPos(mapID, vec)
    if not pos then return nil end
    local wx, wy = pos:GetXY()
    return instance, wx, wy
end

local function ZoneWorld(zoneID)
    local c = worldCache[zoneID]
    if c then return c end
    c = {}
    local list = ns.pins[zoneID]
    for i = 1, #list, 3 do
        local inst, wx, wy = WorldPos(zoneID, list[i + 1], list[i + 2])
        if inst then
            c[#c + 1] = { inst, wx, wy, list[i], list[i + 1], list[i + 2] }
        end
    end
    worldCache[zoneID] = c
    return c
end

local function OnEnter(self)
    ns.ShowTooltip(self, self.giver, false)
end
local function OnLeave()
    GameTooltip:Hide()
end

local function GetPin()
    used = used + 1
    local p = pool[used]
    if not p then
        p = CreateFrame("Frame", nil, Minimap)
        p:SetFrameStrata(Minimap:GetFrameStrata())
        p:SetFrameLevel(Minimap:GetFrameLevel() + 5)
        p.icon = p:CreateTexture(nil, "OVERLAY")
        p.icon:SetAllPoints()
        p:SetScript("OnEnter", OnEnter)
        p:SetScript("OnLeave", OnLeave)
        p:EnableMouse(true)
        pool[used] = p
    end
    return p
end

-- Hide pins beyond the ones placed this update (reusing the same frames in order
-- avoids tooltip flicker on the pin under the mouse).
local function HideUnused()
    for i = used + 1, #pool do pool[i]:Hide() end
end

local function IsIndoors()
    local zoom = Minimap:GetZoom()
    local outdoor = tonumber(GetCVar("minimapZoom"))
    local inside = tonumber(GetCVar("minimapInsideZoom"))
    return inside == zoom and outdoor ~= zoom
end

local Place

local function Update()
    used = 0
    Place()
    HideUnused()
end

Place = function()
    if not (ns.ready and ns.db.minimap) then return end

    local mapID = C_Map.GetBestMapForUnit("player")
    if not mapID then return end
    local pos = C_Map.GetPlayerMapPosition(mapID, "player")
    if not pos then return end -- e.g. inside instances
    local px, py = pos:GetXY()
    if not px then return end

    local inst, pwx, pwy = WorldPos(mapID, px, py)
    if not inst then return end
    -- Measure the map's east and north directions in world space (unit vectors).
    local _, ex1, ey1 = WorldPos(mapID, 0, 0)
    local _, ex2, ey2 = WorldPos(mapID, 1, 0)
    local _, nx2, ny2 = WorldPos(mapID, 0, 1)
    if not (ex1 and ex2 and nx2) then return end
    local eX, eY = ex2 - ex1, ey2 - ey1
    local nX, nY = ex1 - nx2, ey1 - ny2 -- map y grows south
    local el, nl = sqrt(eX * eX + eY * eY), sqrt(nX * nX + nY * nY)
    if el == 0 or nl == 0 then return end
    eX, eY, nX, nY = eX / el, eY / el, nX / nl, nY / nl

    local zoom = Minimap:GetZoom() or 0
    local diameter = (IsIndoors() and SIZE.indoor or SIZE.outdoor)[zoom] or 466
    local radiusYards = diameter / 2
    local radiusPx = Minimap:GetWidth() / 2
    local scale = radiusPx / radiusYards

    local rotate = GetCVar("rotateMinimap") == "1"
    local facing = rotate and GetPlayerFacing and GetPlayerFacing() or 0
    local fs, fc = sin(facing), cos(facing)
    local size = 12 * (ns.db.minimapScale or 1)
    local edge = radiusPx - size / 3

    for zoneID in pairs(ns.pins) do
        for _, e in ipairs(ZoneWorld(zoneID)) do
            if e[1] == inst then
                local dx, dy = e[2] - pwx, e[3] - pwy
                if dx * dx + dy * dy <= radiusYards * radiusYards * 1.2 then
                    local icon, trivial = ns.IconFor(e[4])
                    if icon then
                        local east = dx * eX + dy * eY
                        local north = dx * nX + dy * nY
                        local sx, sy = east, north
                        if rotate then
                            sx = east * fc + north * fs
                            sy = -east * fs + north * fc
                        end
                        sx, sy = sx * scale, sy * scale
                        if sx * sx + sy * sy <= edge * edge then
                            local p = GetPin()
                            p.giver = e[4]
                            p:SetSize(size, size)
                            p.icon:SetTexture(icon)
                            p.icon:SetDesaturated(trivial and true or false)
                            p:ClearAllPoints()
                            p:SetPoint("CENTER", Minimap, "CENTER", sx, sy)
                            p:Show()
                        end
                    end
                end
            end
        end
    end
end

local driver = CreateFrame("Frame")
local elapsed = 0
driver:SetScript("OnUpdate", function(_, dt)
    elapsed = elapsed + dt
    if elapsed < 0.05 then return end
    elapsed = 0
    if Minimap:IsVisible() then Update() end
end)

table.insert(ns.listeners, Update)
