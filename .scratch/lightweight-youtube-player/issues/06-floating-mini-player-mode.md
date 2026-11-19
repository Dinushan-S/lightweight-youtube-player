# 06: Floating Mini-Player Mode & Always-on-Top Pinning

**What to build:** One-click toggle (`Ctrl + M`) between the full library window and an ultra-compact `340x80 px` floating widget. Shows track title, play/pause, skip, mini seek slider, and an Always-on-Top toggle pin so it can float over IDEs while coding.

**Blocked by:** 02: Interactive Timeline & Live Seek Bar

**Status:** ready-for-agent

- [ ] View toggle state in `PlayerController` (`full` vs `mini`)
- [ ] Compact `340x80 px` geometry mode with minimal widget tree
- [ ] Always-on-Top window level toggle with visual pin icon state
- [ ] Smooth transition preserving active playback and seek bar state
- [ ] Automated tests asserting view state transitions and pin status through `PlayerController`
