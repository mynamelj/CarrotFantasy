local cls = ...
local test = cls.addGameLayerMoney
local output = {}
local noop = function() end
local modes = { "GAMEMODE_THEME", "GAMEMODE_WEEKLY", "GAMEMODE_WEEKLY_LOCAL", "GAMEMODE_DAILY_MATCH", "GAMEMODE_STAR_WAY", "GAMEMODE_CANDY", "GAMEMODE_COLLECT" }
modes[#modes+1] = "GAMEMODE_COOPERATION"
local real_env = getfenv(test)
local env = setmetatable({
    _data = {
        StatisticData = {addGetMoneyNum = noop},
        StarWayData = { getTaskType = function() return -999 end }
    },
    _validator = {MoneyDataValidator = {addMoney = noop, subMoney = noop}}
}, {__index=real_env})
env._gl = setmetatable({}, {__index=real_env._gl})
local value = 10000
local money = {
    addValue = function(self, n) value = value+n end,
    getValue = function() return value end
}
local fake = {
    money = money, gameState=-999, getChildByTag=function() return nil end,
    spTopToolBar={updateMoney=noop},
    chessBoard={moneyChangeUpdateInfo=noop},
    getPvpViewPattern=function() return -999 end
}
local function run()
    setfenv(test, env)
    for _, mode in ipairs(modes) do
        env._gl.playerGameMode=env._gl.gameMode[mode]
        local errors=0
        for i=1,500 do
            local before=value
            local amount=(i%7==0) and -20 or 40
            local reason=(i%11==0) and env._gl.moneyChangeType.MONEY_CHANGE_TOWER_SELL or nil
            local expected=(amount>0 and reason~=env._gl.moneyChangeType.MONEY_CHANGE_TOWER_SELL) and amount*10 or amount
            test(fake,amount,reason)
            if value-before~=expected then
                errors=errors+1
                if errors<5 then
                    output[#output+1]=mode.." iteration="..i.." delta="..(value-before).." expected="..expected
                end
            end
        end
        output[#output+1]=mode.." id="..tostring(env._gl.playerGameMode).." errors="..errors
    end
end
local ok,err=pcall(run)
setfenv(test,real_env)
output[#output+1]="native-test="..tostring(ok).." "..tostring(err)
output[#output+1]="jit="..tostring(jit and select(1,jit.status()))
local f=io.open("/data/user/0/com.feiyu.luobo4/files/.carrot_coin_selftest.log","a")
if f then f:write(table.concat(output,"\n"),"\n") f:close() end
