# Growbox Windows app

The GrowBox phone app as a Windows window: a sidebar with Home, Scheduler
and Settings, the same cards, colours, rules and ESP API calls as the
[app](https://github.com/growbox-DIY/app) and the GrowBox macOS app. Cards, chart and
the ESP client come from the [Windows widget](https://github.com/growbox-DIY/windows-widget).

- **Home** (two columns): temperature and humidity, the climate chart with
  target bands and the flowering start (click it: 24 h / 7 days), the
  flowering week, fan and humidifier, the week's nutrients (Auto) or the
  veg nutrients (Manual), "End of period" from week 9, and the last
  watering with the Feeded button (confirm step, locked for 24 h).
- **Scheduler**: light on/off times (Auto mode only).
- **Settings**: Manual / Auto; light, fan, Auto fan, day fan level
  (Manual); flowering start, fan speed, night fan and its level (Auto);
  the OLED display and the TFT monitor (on/off, brightness).
- **Reminders** (Windows notifications, while the app runs): day 3 without
  a watering from 19:00, then from day 4 every 2 h between 8:00 and 22:00.
- Finds the ESP again if its address changes (`esp32.local`, then the
  local /24 network).

## Install

1. Python (once): `winget install Python.Python.3.12` in a terminal (or
   the installer from python.org with "Add to PATH" checked).
2. Copy this folder (with `assets`) to the Windows computer.
3. Double-click `install.bat`. It installs Pillow, adds GrowBox to the
   Start menu and the desktop, and starts it.
4. On first start it asks for the main ESP's API token (the same one the
   app uses).

Settings (ESP address, token, window size) are stored in
`%APPDATA%\GrowBoxDesktop\settings.json`, the week of history in
`history.json` next to it.

`growbox_desktop.pyw --snapshot home.png [--chart-week]` renders the Home
cards to a PNG and quits.

## Files

```
growbox_desktop.pyw  the window: sidebar, Home, Scheduler, Settings
growbox_core.py      ESP client and search, history, reminders, card drawing
assets/              Ionicons font (MIT)
install.bat          Pillow, shortcuts, first start
```

## License

This project is licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/):
you may use, share and modify it for non-commercial purposes, with credit to
growbox-DIY. See LICENSE.
