# 07: Windows Hardware Media Keys & System Tray Integration

**What to build:** Background productivity support. System-wide keyboard and headset media keys (`Play/Pause`, `Next`, `Prev`) control audio even when working in other full-screen apps. Minimizing or closing the window docks the player to the Windows System Tray with a right-click context menu.

**Blocked by:** 06: Floating Mini-Player Mode & Always-on-Top Pinning

**Status:** ready-for-agent

- [ ] Global Windows media key listener (`VK_MEDIA_PLAY_PAUSE`, `VK_MEDIA_NEXT_TRACK`, `VK_MEDIA_PREV_TRACK`)
- [ ] System tray integration (`pystray`) with dynamic Play/Pause, Next, and Quit actions
- [ ] Window close/minimize interceptor docking to tray
- [ ] Automated tests asserting media key events map to `PlayerController` actions
