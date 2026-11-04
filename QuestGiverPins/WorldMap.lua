-- World map pins via a MapCanvas data provider.
local _, ns = ...

local TEMPLATE = "QuestGiverPinsMapPinTemplate"

QuestGiverPinsMapPinMixin = CreateFromMixins(MapCanvasPinMixin)

function QuestGiverPinsMapPinMixin:OnLoad()
    if self.SetScalingLimits then
        self:SetScalingLimits(1, 1.0, 1.2)
    end
end

function QuestGiverPinsMapPinMixin:OnAcquired(info)
    self.info = info
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

local function AddZonePins(map, zoneID, rect)
    local list = ns.pins[zoneID]
    if not list then return end
    for i = 1, #list, 3 do
        local giver = list[i]
        local icon, trivial = ns.IconFor(giver)
        if icon then
            local x, y = list[i + 1], list[i + 2]
            local px, py = x, y
            if rect then
                px = rect.minX + x * (rect.maxX - rect.minX)
                py = rect.minY + y * (rect.maxY - rect.minY)
            end
            map:AcquirePin(TEMPLATE, {
                giver = giver, icon = icon, trivial = trivial, small = rect ~= nil,
                x = px, y = py, wpMap = zoneID, wpX = x, wpY = y,
            })
        end
    end
end

function Provider:RefreshAllData()
    self:RemoveAllData()
    if not (ns.ready and ns.db.worldMap) then return end
    local map = self:GetMap()
    local mapID = map:GetMapID()
    if not mapID then return end

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

table.insert(ns.listeners, function()
    if WorldMapFrame:IsShown() then
        Provider:RefreshAllData()
    end
end)
