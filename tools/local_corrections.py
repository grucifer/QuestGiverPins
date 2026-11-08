"""Fixes on top of Questie's data, applied by extract.py after the merge.
Keyed by quest ID; values use the short field names extract.py writes (see its qout dict).
Each entry says why, so it can be dropped once Questie fixes it upstream."""

QUESTS = {
    # Trek to Ashenvale: Sentinel Selarin only appears in Auberdine (scripted scene with Terenthis)
    # after "A Lost Master" (986) is turned in. Questie has no prerequisite, so the ! showed too early.
    990: {"ps": [986]},
}
