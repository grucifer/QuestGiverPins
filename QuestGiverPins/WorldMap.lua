-- World map pins via a MapCanvas data provider.
-- With OpenMap (seamless stitched map) installed, pins are placed through OpenMapAPI so they line up
-- on the stitched map, show neighbouring zones' givers too, and sit above OpenMap's map art.
local _, ns = ...

local TEMPLATE = "QuestGiverPinsMapPinTemplate"
local abs = math.abs

QuestGiverPinsMapPinMixin = CreateFromMixins(MapCanvasPinMixin)

function QuestGiverPinsMapPinMixin:OnLoad()
    if self.SetScalingLimits then
        self:SetScalingLimits(1, 1.0, 1.2)
    end
end

function QuestGiverPinsMapPinMixin:OnAcquired(info)
    self.info = info
    -- a pin lifted for OpenMap earlier goes back to normal frame-level handling
    if self.qgpLifted and self.SetFixedFrameLevel and not InCombatLockdown() then
        self:SetFixedFrameLevel(false)
        self.qgpLifted = nil
    end
    local size = 16 * (ns.db and ns.db.mapScale or 1) * (info.small and 0.75 or 1)
    self:SetSize(size, size)
    self.Icon:SetTexture(info.icon)
    self.Icon:SetDesaturated(info.trivial and true or false)
    self.Icon:SetAlpha(info.trivial and 0.7 or 1)
    self:SetPosition(info.x, info.y)
end

function QuestGiverPinsMapPinMixin:OnMouseEnter()
    ns.ShowTooltip(self, self.info.giver, true)
end

function QuestGiverPinsMapPinMixin:OnMouseLeave()
    GameTooltip:Hide()
end

function QuestGiverPinsMapPinMixin:OnMouseClickAction(button)
    if button == "LeftButton" and self.info then
        ns.SetWaypoint(self.info.wpMap, self.info.wpX, self.info.wpY)
    end
end

local Provider = CreateFromMixins(MapCanvasDataProviderMixin)

function Provider:RemoveAllData()
    self:GetMap():RemoveAllPinsByTemplate(TEMPLATE)
end

local function Acquire(map, giver, zoneID, x, y, px, py, small)
    local icon, trivial = ns.IconFor(giver)
    if not icon then return end
    return map:AcquirePin(TEMPLATE, {
        giver = giver, icon = icon, trivial = trivial, small = small,
        x = px, y = py, wpMap = zoneID, wpX = x, wpY = y,
    })
end

local function AddZonePins(map, zoneID, rect)
    local list = ns.pins[zoneID]
    if not list then return end
    for i = 1, #list, 3 do
        local x, y = list[i + 1], list[i + 2]
        local px, py = x, y
        if rect then
            px = rect.minX + x * (rect.maxX - rect.minX)
            py = rect.minY + y * (rect.maxY - rect.minY)
        end
        Acquire(map, list[i], zoneID, x, y, px, py, rect ~= nil)
    end
end

---------------------------------------------------------------------------
-- OpenMap support
---------------------------------------------------------------------------
local NEAR = 0.5       -- on a zone: pins this far (in map widths) beyond the zone underneath
local VIEW_NEAR = 1.5  -- on a continent: pins within this many half-views of the view's centre

local function OpenMapStitched()
    local api = _G.OpenMapAPI
    return api and api.IsStitched and api.IsStitched() and api or nil
end

local function Lift(pin, top)
    if not (pin and top) or InCombatLockdown() then return end
    if pin:GetFrameLevel() > top then return end
    if pin.SetFixedFrameLevel then pin:SetFixedFrameLevel(false) end
    pin:SetFrameLevel(top + 2)
    if pin.SetFixedFrameLevel then pin:SetFixedFrameLevel(true) end
    pin.qgpLifted = true
end

local function AddStitchedPins(map, api, hostID)
    local info = C_Map.GetMapInfo(hostID)
    local mapType = info and info.mapType
    local UIMapType = Enum and Enum.UIMapType
    if UIMapType and (mapType == UIMapType.World or mapType == UIMapType.Cosmic) then return end
    local onContinent = UIMapType and mapType == UIMapType.Continent

    local cu, cv, half
    if onContinent then
        local u, v, zoom = api.GetView()
        if not u then return end
        cu, cv, half = u, v, VIEW_NEAR * 0.5 / math.max(zoom or 1, 1)
    end
    local top = api.ArtTopLevel and api.ArtTopLevel()

    for zoneID, list in pairs(ns.pins) do
        for i = 1, #list, 3 do
            local x, y = list[i + 1], list[i + 2]
            local u, v = api.WorldFromMap(zoneID, x, y)
            if u then
                local keep = true
                if onContinent then keep = abs(u - cu) <= half and abs(v - cv) <= half end
                if keep then
                    local px, py = api.MapFromWorld(hostID, u, v)
                    if px and (onContinent or (px >= -NEAR and px <= 1 + NEAR and py >= -NEAR and py <= 1 + NEAR)) then
                        Lift(Acquire(map, list[i], zoneID, x, y, px, py, onContinent), top)
                    end
                end
            end
        end
    end
end

---------------------------------------------------------------------------

function Provider:RefreshAllData()
    self:RemoveAllData()
    if not (ns.ready and ns.db.worldMap) then return end
    local map = self:GetMap()
    local mapID = map:GetMapID()
    if not mapID then return end

    local api = OpenMapStitched()
    if api then
        AddStitchedPins(map, api, mapID)
        return
    end

    if ns.pins[mapID] then
        AddZonePins(map, mapID, nil)
        return
    end

    if ns.db.continent then
        local info = C_Map.GetMapInfo(mapID)
        if info and Enum and Enum.UIMapType and info.mapType == Enum.UIMapType.Continent then
            for zoneID in pairs(ns.pins) do
                local minX, maxX, minY, maxY = C_Map.GetMapRectOnMap(zoneID, mapID)
                if minX and maxX > minX then
                    AddZonePins(map, zoneID, { minX = minX, maxX = maxX, minY = minY, maxY = maxY })
                end
            end
        end
    end
end

function Provider:OnMapChanged()
    self:RefreshAllData()
end

WorldMapFrame:AddDataProvider(Provider)

local function RefreshIfShown()
    if WorldMapFrame:IsShown() then
        Provider:RefreshAllData()
    end
end
table.insert(ns.listeners, RefreshIfShown)

-- OpenMap: redraw as the stitched view moves (it sends this a few times a second at most) or switches,
-- and add an on/off switch to OpenMap's own map menu.
local function HookOpenMap()
    local api = _G.OpenMapAPI
    if not api or ns.openMapHooked then return end
    ns.openMapHooked = true
    if api.RegisterCallback then
        api.RegisterCallback(ns, "OpenMap_StitchedChanged", RefreshIfShown)
        api.RegisterCallback(ns, "OpenMap_ViewChanged", function()
            local mapID = WorldMapFrame:IsShown() and WorldMapFrame:GetMapID()
            local info = mapID and C_Map.GetMapInfo(mapID)
            if info and Enum and Enum.UIMapType and info.mapType == Enum.UIMapType.Continent then
                Provider:RefreshAllData()
            end
        end)
    end
    if api.RegisterMenuToggle then
        api.RegisterMenuToggle("QuestGiverPins", {
            id = "pins",
            label = "Quest giver pins",
            icon = ns.ICON_AVAILABLE,
            section = "Quest Giver Pins",
            get = function() return ns.db and ns.db.worldMap end,
            set = function(on)
                if not ns.db then return end
                ns.db.worldMap = on and true or false
                ns.NotifyChanged()
            end,
        })
    end
end
HookOpenMap()

local ev = CreateFrame("Frame")
ev:RegisterEvent("PLAYER_LOGIN")
ev:RegisterEvent("PLAYER_REGEN_ENABLED") -- pins can't be lifted above OpenMap's art in combat: redo after
ev:SetScript("OnEvent", function(_, event)
    if event == "PLAYER_LOGIN" then HookOpenMap() end
    if OpenMapStitched() then RefreshIfShown() end
end)
