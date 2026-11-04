# Quest Giver Pins

A lightweight **World of Warcraft: Forever** addon (interface 16001) that puts a **!** on the world map and minimap for every quest giver with a quest you can pick up right now. It shows only quest-giver pins, without the rest of Questie.

See [`QuestGiverPins/README.md`](QuestGiverPins/README.md) for install steps and `/qgp` commands.

## Install
Copy the `QuestGiverPins` folder into `World of Warcraft\_forever_\Interface\AddOns\`.

## Rebuilding the quest data
`QuestGiverPins/Data.lua` is generated from [QuestieDB](https://github.com/Questie/QuestieDB) (Forever base data plus all Forever corrections) and [Questie](https://github.com/Questie/Questie)'s quest blacklist. The extractor parses their Lua data as text and doesn't execute anything from those repos.

```sh
git clone --depth 1 https://github.com/Questie/QuestieDB vendor/QuestieDB
git clone --depth 1 https://github.com/Questie/Questie   vendor/Questie
python3 tools/extract.py          # writes QuestGiverPins/Data.lua
pip install lupa && python3 tools/test_addon.py   # offline tests with stubbed WoW APIs
```

## License
GPL-3.0, because the quest data is derived from Questie/QuestieDB (GPL-3.0).
