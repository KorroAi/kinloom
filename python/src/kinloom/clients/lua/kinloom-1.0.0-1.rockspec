rockspec_format = "3.0"
package = "kinloom"
version = "1.0.0-1"
source = {
  url = "git+https://github.com/KorroAi/kinloom.git",
}
description = {
  summary = "Kinloom SDK for Lua games (LÖVE, Defold, Solar2D, LuaJIT, Lua 5.1-5.4)",
  license = "MIT",
  detailed = "AI that decides, writes, acts and talks in your game, calling the model itself or a relay, and answering offline with your own lines and examples.",
}
dependencies = {
  "lua >= 5.1",
}
build = {
  type = "builtin",
  modules = {
    kinloom = "python/src/kinloom/clients/lua/kinloom.lua",
  },
}
