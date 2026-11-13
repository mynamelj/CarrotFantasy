local board = ...
local get_build_selection_ids = assert(board.getBuildSelectionIds)
local solo_mode_names = {
    "GAMEMODE_THEME", "GAMEMODE_WEEKLY", "GAMEMODE_WEEKLY_LOCAL",
    "GAMEMODE_DAILY_MATCH", "GAMEMODE_STAR_WAY", "GAMEMODE_CANDY", "GAMEMODE_COLLECT",
}
local extra_tower_names = {"TOWER_SUN", "TOWER_CRYSTAL"}

function board:getBuildSelectionIds()
    local gl = _gl
    local mode = gl.playerGameMode
    local solo = false
    for _, name in ipairs(solo_mode_names) do
        if mode and mode == gl.gameMode[name] then
            solo = true
            break
        end
    end
    local ids = gl.inGameTowerIDList
    if solo and ids and ids[1] then
        -- Keep the in-game list in sync with menu refresh and dismissal.
        local extended = {}
        local present = {}
        for i, id in ipairs(ids) do
            extended[i] = id
            present[id] = true
        end
        for _, name in ipairs(extra_tower_names) do
            local id = gl.tower[name]
            if id and not present[id] and _data.TowerData[id] and _json.turret_proto[id .. "_1"] then
                extended[#extended + 1] = id
                present[id] = true
            end
        end
        if #extended > #ids then
            gl.inGameTowerIDList = extended
        end
    end
    return get_build_selection_ids(self)
end
