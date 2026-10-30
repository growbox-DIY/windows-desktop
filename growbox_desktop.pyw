# growbox_desktop.pyw - the GrowBox phone app as a Windows window: a sidebar
# with Home, Scheduler and Settings, the same cards, colours, rules and ESP
# API calls as the app (and growbox-macos-desktop).
#
# Cards, chart, ESP client and search come from the Windows widget
# (growbox_core.py). Settings (ESP address, token) are kept in
# %APPDATA%\GrowBoxDesktop\settings.json, the week of history next to it.
#
#   pyw growbox_desktop.pyw
#   python growbox_desktop.pyw --snapshot home.png [--chart-week]
import datetime as dt
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog

from PIL import Image, ImageTk

import growbox_core as core

APP = "GrowBox"
SCALE = 1.5

BG = "#011515"
SURFACE = "#041C1B"
SURFACE_LIGHT = "#062523"
TEXT = "#F2F5F4"
MUTED = "#8A9B9B"
GREEN = "#00E95A"
CYAN = "#20DCE8"
BLUE = "#78BFFF"
YELLOW = "#FFD21C"
RED = "#FF6070"
BORDER = "#123333"

FONT = "Segoe UI" if sys.platform == "win32" else "Helvetica"

# BioBizz doses per 1 L of water, our week -> BioBizz week + 2
# (data/fertilizerSchedule.ts in the app)
NUTRIENT_COLORS = {
    "BIO·GROW": "#76BC7A", "BIO·BLOOM": "#F1604C", "TOP·MAX": "#D85A61",
    "BIO·HEAVEN": "#5CCAD6", "ACTI·VERA": "#9BC86A",
}
NAMES = ("BIO·GROW", "BIO·BLOOM", "TOP·MAX", "BIO·HEAVEN", "ACTI·VERA")
VEG = (2, 0, 0, 2, 2)
SCHEDULE = {
    1: (2, 1, 1, 2, 2), 2: (2, 2, 1, 2, 2), 3: (3, 2, 1, 3, 3), 4: (3, 3, 1, 4, 4),
    5: (4, 3, 1, 4, 4), 6: (4, 4, 4, 5, 5), 7: (4, 4, 4, 5, 5), 8: (4, 4, 4, 5, 5),
    9: (4, 4, 4, 5, 5), 10: (4, 4, 4, 5, 5),
}
TOTAL_WEEKS = 10
# from this week on nothing is fed any more: the period ends
END_OF_PERIOD_WEEK = 9

# the card areas of the widget panel (growbox_core.Painter.render)
SENSOR = (12, 40, 328, 102)
CHART = (12, 112, 328, 246)
STATUS = (12, 256, 328, 361)
FEEDING = (12, 371, 328, 425)

# on a Mac (layout checks) keep the files out of the home folder
if sys.platform != "win32" and not os.environ.get("APPDATA"):
    core.APP_DIR = os.path.expanduser("~/Library/Application Support/GrowBoxDesktop")
    core.SETTINGS_FILE = os.path.join(core.APP_DIR, "settings.json")
    core.HISTORY_FILE = os.path.join(core.APP_DIR, "history.json")


def label(parent, text, size=11, color=TEXT, bold=False, bg=SURFACE, **kw):
    return tk.Label(parent, text=text, fg=color, bg=bg,
                    font=(FONT, size, "bold" if bold else "normal"), **kw)


def button(parent, text, command, color=GREEN, fg=SURFACE_LIGHT):
    return tk.Button(parent, text=text, command=command, bg=color, fg=fg, activebackground=color,
                     activeforeground=fg, relief="flat", bd=0, padx=14, pady=5,
                     font=(FONT, 10, "bold"), cursor="hand2", highlightthickness=0)


def card(parent, **kw):
    return tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1, **kw)


class Box:
    """What the screens need from /api/config, read like the app's store
    (context/BoxControllerContext.tsx)."""

    def __init__(self, response):
        self.response = response
        r = response or {}
        self.config = r.get("config") or {}
        self.status = r.get("status") or {}

    def get(self, *path, default=None):
        node = self.config

        for key in path:
            if not isinstance(node, dict):
                return default
            node = node.get(key)

        return default if node is None else node

    mode = property(lambda self: self.status.get("mode") or "MANUAL")
    light = property(lambda self: bool(self.get("relayLight", "state")))
    fan = property(lambda self: bool(self.get("relayFan", "state")))
    fan_auto = property(lambda self: bool(self.get("fanAuto", "enabled")))
    night_fan = property(lambda self: bool(self.get("auto", "nightFan", "enabled")))
    display = property(lambda self: bool(self.get("display", "enabled")))
    day_level = property(lambda self: self.get("dimmer", "day", "level", default=50))
    night_level = property(lambda self: self.get("dimmer", "night", "level", default=30))
    start_date = property(lambda self: self.get("auto", "floweringStartDate"))

    @property
    def schedule(self):
        items = self.get("lightSchedule", default=[])
        return items[0] if items else None

    @property
    def monitor(self):
        # only while the monitor is plugged in and polling the ESP
        return self.get("monitor") if self.status.get("monitorOnline") else None


class App:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot
        self.settings = core.load_settings()
        core.set_dpi_awareness()

        self.root = tk.Tk()
        self.root.title(APP)
        self.root.configure(bg=BG)
        self.root.geometry(self.settings.get("geometry", "1060x760"))
        self.root.minsize(900, 620)

        if not self.settings.get("token"):
            self.settings.update(self.mac_widget_settings())

        if not self.settings.get("token") and not snapshot:
            token = simpledialog.askstring(
                APP, "Paste the API token of the main ESP\n(the same one the app uses):", parent=self.root)

            if not token:
                self.root.destroy()
                sys.exit(0)

            self.settings["token"] = token.strip()
            self.save()

        self.painter = core.Painter(SCALE)
        self.week = "--chart-week" in sys.argv
        self.page = "Home"
        self.busy = False
        self.error = None
        self.images = {}
        self.seen = None

        self.poller = core.Poller(self.settings.get("url") or core.DEFAULT_URL,
                                  self.settings.get("token", ""), self.url_changed)
        self.poller.start()
        self.build()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.tick()

    # --- settings ---

    @staticmethod
    def mac_widget_settings():
        """On a Mac, for checking the layout: the macOS widget's settings."""
        path = os.path.expanduser("~/.config/growbox/widget.json")

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return {"url": data["url"], "token": data["token"]}
        except (OSError, ValueError, KeyError):
            return {}

    def save(self):
        if not self.snapshot:
            core.save_settings(self.settings)

    def url_changed(self, url):
        self.settings["url"] = url
        self.save()

    def quit(self):
        self.settings["geometry"] = self.root.geometry()
        self.save()
        self.root.destroy()

    # --- writes: the app's calls, then a fresh /config ---

    def send(self, path, body=None, then=None):
        if self.busy:
            return

        self.busy = True

        def run():
            try:
                core.post_json(self.poller.url, "/api" + path, self.poller.token, body)
                ok, self.error = True, None
            except Exception:
                ok, self.error = False, "Could not reach the controller"

            self.busy = False
            self.poller.refresh()

            if then:
                self.root.after(0, lambda: then(ok))

        threading.Thread(target=run, daemon=True).start()

    # --- window ---

    def build(self):
        side = tk.Frame(self.root, bg=SURFACE, width=170)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        label(side, "GrowBox", 16, GREEN, True).pack(anchor="w", padx=18, pady=(20, 18))
        self.nav = {}

        for name in ("Home", "Scheduler", "Settings"):
            item = label(side, name, 12, MUTED, cursor="hand2", anchor="w", padx=18, pady=8)
            item.pack(fill="x")
            item.bind("<Button-1>", lambda _e, n=name: self.show(n))
            self.nav[name] = item

        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(side="left", fill="both", expand=True, padx=20, pady=16)
        self.show("Home")

    def show(self, page):
        self.page = page

        for name, item in self.nav.items():
            item.configure(fg=GREEN if name == page else MUTED,
                           font=(FONT, 12, "bold" if name == page else "normal"))

        for child in self.body.winfo_children():
            child.destroy()

        self.view = None
        self.seen = None
        self.render()

    def header(self, title, box):
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", pady=(0, 12))
        label(row, title, 20, TEXT, True, bg=BG).pack(side="left")
        state = core.build_state(self.poller)

        if state["searching"]:
            text, color = "Searching for the box…", MUTED
        elif state["loading"]:
            text, color = "Connecting…", MUTED
        elif state["error"]:
            text, color = state["error"], RED
        else:
            text, color = box.mode, GREEN

        label(row, text, 10, color, True, bg=BG).pack(side="right")

        if self.error:
            label(row, self.error, 10, RED, bg=BG).pack(side="right", padx=12)

    def tick(self):
        state_key = (self.poller.version, self.week, self.busy, self.error, dt.datetime.now().strftime("%H:%M"))

        if state_key != self.seen:
            self.seen = state_key
            self.render()

            if self.poller.response is not None:
                core.alert_if_feeding_missed(core.build_state(self.poller)["box"], self.settings, self.save)

        if self.snapshot and self.poller.response is not None and self.poller.readings:
            self.root.after(1500, self.save_snapshot)
            self.snapshot_done = True
            return

        self.root.after(500, self.tick)

    def render(self):
        # rebuilt on every change; a slider being dragged keeps its page
        if getattr(self, "dragging", False):
            return

        for child in self.body.winfo_children():
            child.destroy()

        box = Box(self.poller.response)
        {"Home": self.home, "Scheduler": self.scheduler, "Settings": self.settings_page}[self.page](box)

    # --- Home: the widget's cards in two columns, plus the app's extras ---

    def cards(self):
        core.SPAN = dt.timedelta(days=7) if self.week else dt.timedelta(hours=24)
        panel, _ = self.painter.render(core.build_state(self.poller))
        return {name: panel.crop(tuple(round(v * SCALE) for v in area))
                for name, area in (("sensor", SENSOR), ("chart", CHART), ("status", STATUS), ("feeding", FEEDING))}

    def picture(self, parent, image, name, **kw):
        photo = ImageTk.PhotoImage(image)
        self.images[name] = photo
        widget = tk.Label(parent, image=photo, bg=BG, bd=0, **kw)
        widget.pack(anchor="nw", pady=(0, 10))
        return widget

    def home(self, box):
        self.header("Home", box)
        cols = tk.Frame(self.body, bg=BG)
        cols.pack(fill="both", expand=True)
        left, right = tk.Frame(cols, bg=BG), tk.Frame(cols, bg=BG)
        left.pack(side="left", anchor="n", padx=(0, 14))
        right.pack(side="left", anchor="n", fill="x", expand=True)
        images = self.cards()

        self.picture(left, images["sensor"], "sensor")
        chart = self.picture(left, images["chart"], "chart", cursor="hand2")
        # click: 24 h <-> 7 days, like a tap in the app
        chart.bind("<Button-1>", lambda _e: self.toggle_week())

        self.picture(right, images["status"], "status")

        if box.response is not None:
            if box.mode == "AUTO":
                self.flowering_section(right, box)
            else:
                self.nutrients(right, "Veg nutrients", VEG)

        self.picture(right, images["feeding"], "feeding")

        if box.response is not None:
            self.feed_button(right, box)

    def toggle_week(self):
        self.week = not self.week
        self.render()

    def nutrients(self, parent, title, doses):
        frame = card(parent, padx=14, pady=10)
        frame.pack(fill="x", pady=(0, 10))
        top = tk.Frame(frame, bg=SURFACE)
        top.pack(fill="x", pady=(0, 6))
        label(top, title, 13, TEXT, True).pack(side="left")
        label(top, "per 1 L", 9, MUTED).pack(side="right")

        for name, ml in zip(NAMES, doses):
            if not ml:
                continue
            row = tk.Frame(frame, bg=SURFACE)
            row.pack(fill="x")
            label(row, name, 11, NUTRIENT_COLORS[name], True).pack(side="left")
            label(row, "%d ml" % ml, 11, TEXT, True).pack(side="right")

    def flowering_section(self, parent, box):
        state = core.build_state(self.poller)
        week = (state["box"].flowering_week or (1, 0))[0]

        if not box.start_date:
            info = card(parent, padx=14, pady=10)
            info.pack(fill="x", pady=(0, 10))
            label(info, "Start flowering first", 13, TEXT, True).pack(anchor="w")
            label(info, "Start flowering in Auto mode to see the flowering schedule and nutrients.",
                  10, MUTED, wraplength=380, justify="left").pack(anchor="w")
            button(info, "Start flowering", self.start_flowering).pack(anchor="w", pady=(8, 0))
        elif week >= END_OF_PERIOD_WEEK:
            end = card(parent, padx=14, pady=10)
            end.pack(fill="x", pady=(0, 10))
            label(end, "End of period", 13, CYAN, True).pack(anchor="w")
            label(end, "Water only", 10, MUTED).pack(anchor="w")
            button(end, "Finish", self.finish_period, color=CYAN).pack(anchor="w", pady=(8, 0))
        else:
            self.nutrients(parent, "Nutrients schedule", SCHEDULE.get(week, ()))

    def start_flowering(self):
        if messagebox.askyesno(APP, "Start flowering today?", parent=self.root):
            self.send("/flowering/start-date", {"date": dt.date.today().isoformat()})

    def finish_period(self):
        """EndOfPeriodCard: erase the sensor log, then switch to Manual."""
        if not messagebox.askyesno(
                "Finish the period?",
                "This erases all sensor logs on the SD card and in the app, then switches the box to Manual.",
                icon="warning", parent=self.root):
            return

        def erased(ok):
            if not ok:
                messagebox.showerror("Could not erase the logs", "Check the connection and try again.")
                return

            with self.poller.lock:
                self.poller.readings = []
            core.save_history([])

            if Box(self.poller.response).mode == "AUTO":
                self.send("/mode/toggle", then=lambda ok2: ok2 or messagebox.showwarning(
                    "Logs erased", "Could not switch to Manual. Switch the mode by hand."))

        self.send("/environment/erase", then=erased)

    def feed_button(self, parent, box):
        """FeedingCard: a confirm step, then locked for 24 h after a feeding."""
        state = core.build_state(self.poller)["box"]

        if state.fed_recently:
            return

        overdue = state.feeding_status == "overdue"
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x")
        button(row, "Feed me now!" if overdue else "Feeded", self.feed,
               color=RED if overdue else GREEN).pack(side="right")

    def feed(self):
        if messagebox.askyesno(APP, "Save today's watering on the controller?", parent=self.root):
            now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            self.send("/feeding", {"date": now})

    # --- Scheduler: the light schedule, Auto only ---

    def scheduler(self, box):
        self.header("Scheduler", box)
        self.picture(self.body, self.cards()["sensor"], "sensor")

        if box.mode != "AUTO":
            info = card(self.body, padx=16, pady=12)
            info.pack(fill="x")
            label(info, "Auto mode required", 13, TEXT, True).pack(anchor="w")
            label(info, "The scheduler is available only when the system is running in Auto mode.",
                  10, MUTED).pack(anchor="w")
            return

        frame = card(self.body, padx=16, pady=12)
        frame.pack(fill="x")
        label(frame, "Light schedule", 15, TEXT, True).pack(anchor="w")
        label(frame, "Set when the light turns on and off.", 10, MUTED).pack(anchor="w", pady=(0, 8))
        schedule = box.schedule or {"on": "--:--", "off": "--:--"}

        for key in ("on", "off"):
            row = tk.Frame(frame, bg=SURFACE)
            row.pack(fill="x", pady=4)
            label(row, key.upper(), 9, MUTED, True).pack(anchor="w")
            label(row, schedule[key], 22, TEXT, True).pack(side="left")
            button(row, "Change", lambda k=key: self.edit_time(k, box), color=SURFACE_LIGHT,
                   fg=GREEN).pack(side="right")

    def edit_time(self, key, box):
        """Same checks as the app: four digits, hours <= 23, minutes <= 59."""
        if not box.schedule:
            return

        draft = simpledialog.askstring(APP, "%s time (HHMM):" % key.upper(), parent=self.root,
                                       initialvalue=box.schedule[key].replace(":", ""))
        digits = "".join(c for c in (draft or "") if c.isdigit())[:4]

        if len(digits) != 4 or int(digits[:2]) > 23 or int(digits[2:]) > 59:
            return

        time = "%s:%s" % (digits[:2], digits[2:])
        item = dict(box.schedule)
        item[key] = time
        self.send("/light-schedule", [{"on": item["on"], "off": item["off"]}])

    # --- Settings: mode, Manual / Auto controls, OLED, TFT monitor ---

    def settings_page(self, box):
        self.header("Settings", box)

        if box.response is None:
            return

        tabs = tk.Frame(self.body, bg=BG)
        tabs.pack(fill="x", pady=(0, 10))

        for mode, name in (("MANUAL", "Manual"), ("AUTO", "Auto")):
            active = box.mode == mode
            button(tabs, name, (lambda: None) if active else (lambda: self.send("/mode/toggle")),
                   color=GREEN if active else SURFACE_LIGHT, fg=SURFACE_LIGHT if active else MUTED
                   ).pack(side="left", padx=(0, 6))

        if box.mode == "MANUAL":
            self.section("Manual mode", "Control everything manually.")
            self.switch("Light", box.light, "/light/toggle")
            self.switch("Fan", box.fan, "/fan/toggle")
            self.switch("Auto fan", box.fan_auto, "/fan/auto/toggle",
                        status="BY TEMPERATURE" if box.fan_auto else "OFF")
            self.slider("Day fan", box.day_level, lambda v: self.send("/fan/level", {"level": v}),
                        disabled=box.fan_auto)
        else:
            self.section("Auto mode", "Automated growing schedule.")
            self.flowering_start(box)
            self.slider("Fan speed", box.day_level, lambda v: self.send("/fan/level", {"level": v}))
            self.switch("Night fan", box.night_fan, "/auto/night-fan/toggle")
            self.slider("Night dimmer level", box.night_level,
                        lambda v: self.send("/fan/night-level", {"level": v}))

        self.switch("Display", box.display, "/display/toggle")
        monitor = box.monitor

        if monitor:
            enabled = bool(monitor.get("enabled"))
            self.switch("Monitor", enabled, "/monitor", body={"enabled": not enabled})
            self.slider("Monitor brightness", monitor.get("brightness", 100),
                        lambda v: self.send("/monitor", {"brightness": v}), low=5, step=5,
                        disabled=not enabled)

    def section(self, title, subtitle):
        label(self.body, title, 15, TEXT, True, bg=BG).pack(anchor="w")
        label(self.body, subtitle, 10, MUTED, bg=BG).pack(anchor="w", pady=(0, 8))

    def switch(self, title, on, path, body=None, status=None):
        row = card(self.body, padx=14, pady=8)
        row.pack(fill="x", pady=(0, 8))
        label(row, title, 12, TEXT, True).pack(side="left")
        button(row, "ON" if on else "OFF", lambda: self.send(path, body),
               color=GREEN if on else SURFACE_LIGHT, fg=SURFACE_LIGHT if on else MUTED).pack(side="right")

        if status and status not in ("ON", "OFF"):
            label(row, status, 9, GREEN if on else MUTED, True).pack(side="right", padx=10)

    def slider(self, title, value, commit, low=0, step=1, disabled=False):
        """Sends the value once, on release."""
        row = card(self.body, padx=14, pady=8)
        row.pack(fill="x", pady=(0, 8))
        label(row, title, 12, MUTED if disabled else TEXT, True).pack(anchor="w")
        scale = tk.Scale(row, from_=low, to=100, resolution=step, orient="horizontal", bg=SURFACE,
                         fg=GREEN, troughcolor=BORDER, highlightthickness=0, bd=0, sliderrelief="flat",
                         activebackground=GREEN, font=(FONT, 10, "bold"),
                         state="disabled" if disabled else "normal")
        scale.set(value)
        scale.pack(fill="x")

        def press(_e):
            self.dragging = True

        def release(_e):
            self.dragging = False

            if not disabled and int(scale.get()) != value:
                commit(int(scale.get()))

        scale.bind("<ButtonPress-1>", press)
        scale.bind("<ButtonRelease-1>", release)

    def flowering_start(self, box):
        row = card(self.body, padx=14, pady=8)
        row.pack(fill="x", pady=(0, 8))

        if not box.start_date:
            label(row, "Flowering start", 12, TEXT, True).pack(side="left")
            button(row, "Start flowering", self.start_flowering).pack(side="right")
            return

        week = (core.build_state(self.poller)["box"].flowering_week or (1, 0))[0]
        label(row, "%s, Week %d" % (box.start_date, min(week, TOTAL_WEEKS)), 12, TEXT, True).pack(side="left")

        def reset():
            if messagebox.askyesno(APP, "Clear the flowering start?", parent=self.root):
                self.send("/flowering/start-date", {"date": None})

        button(row, "Clear", reset, color=RED).pack(side="right")

    # --- --snapshot: the Home cards to a PNG, for layout checks ---

    def save_snapshot(self):
        images = self.cards()
        chart = images["chart"]
        gap = 15
        w = images["sensor"].width * 2 + gap * 3
        h = max(images["sensor"].height + chart.height, images["status"].height + images["feeding"].height) + gap * 3
        out = Image.new("RGB", (w, h), core.BACKGROUND)
        out.paste(images["sensor"], (gap, gap))
        out.paste(chart, (gap, gap * 2 + images["sensor"].height))
        out.paste(images["status"], (gap * 2 + images["sensor"].width, gap))
        out.paste(images["feeding"], (gap * 2 + images["sensor"].width, gap * 2 + images["status"].height))
        out.save(self.snapshot)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    snapshot = sys.argv[sys.argv.index("--snapshot") + 1] if "--snapshot" in sys.argv else None
    App(snapshot).run()


if __name__ == "__main__":
    main()
