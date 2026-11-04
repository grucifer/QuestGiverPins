# Quest Giver Pins (WoW Forever)

A small addon that shows a yellow **!** on the world map and minimap wherever a quest giver has a quest you can pick up right now. It does nothing else: no quest log, objectives, tracker or database UI.

## Install
1. Unzip so the folder sits at `World of Warcraft\_forever_\Interface\AddOns\QuestGiverPins\`. The `.toc` file must be directly inside `QuestGiverPins`, not in a second nested folder.
2. Restart the game, or `/reload` if you're already logged in. Enable "Quest Giver Pins" in the AddOns list at character select.

## What you see
- **Yellow !**: a quest is available.
- **Blue !**: the giver only has repeatable or daily quests.
- Hover a pin to see the quest names and levels. Click a world-map pin to set a waypoint.

A quest shows only when you meet its requirements. Pins hide quests that are:
- completed or already in your log
- for the wrong race, class or faction
- above your level
- missing a prerequisite or breadcrumb
- missing a required profession, reputation or spell

Gray (trivial) quests are hidden by default.

## Commands (`/qgp`)
| Command | Effect |
|---|---|
| `/qgp map` | toggle world map pins |
| `/qgp minimap` | toggle minimap pins |
| `/qgp continent` | also show pins on continent maps (off by default) |
| `/qgp lowlevel` | show gray/low-level quests |
| `/qgp events` | show holiday/event quests |
| `/qgp repeatable` | toggle repeatable/daily quests |
| `/qgp scale 1.3` / `/qgp minimapscale 1.3` | icon size |
| `/qgp reset` | defaults |

## Data & license
The quest-giver data (`Data.lua`) was extracted from [QuestieDB](https://github.com/Questie/QuestieDB) (Forever base data plus all Forever corrections) and Questie's quest blacklist, both GPL-3.0. This addon is therefore also GPL-3.0 (see LICENSE.txt). Data snapshot: QuestieDB `4ab6431`, Questie `01bb718`, 4 Nov 2026. Quests that start from dropped items aren't shown, since those have no giver to pin.
