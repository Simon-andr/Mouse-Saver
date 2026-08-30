#!/usr/bin/env python3
"""Sauvegarde et restaure la position de la souris via raccourcis clavier."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402
from pynput.keyboard import GlobalHotKeys  # noqa: E402
from pynput.mouse import Controller  # noqa: E402

CONFIG_PATH = Path(__file__).resolve().parent / "settings.json"
DEFAULT_SAVE = "<ctrl>+<shift>+p"
DEFAULT_RESTORE = "<ctrl>+<shift>+r"

MODIFIER_KEYS = {
    "Control_L",
    "Control_R",
    "Shift_L",
    "Shift_R",
    "Alt_L",
    "Alt_R",
    "Meta_L",
    "Meta_R",
    "Super_L",
    "Super_R",
    "ISO_Level3_Shift",
    "Caps_Lock",
    "Num_Lock",
}

CSS = b"""
window, dialog, messagedialog {
  background-color: #0F0E17;
}

.hero {
  background-image: linear-gradient(135deg, #5B46F6 0%, #8F00FF 100%);
  border-radius: 18px;
  padding: 22px 22px 20px 22px;
}

.hero-title {
  color: #FFFFFF;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.2px;
}

.hero-sub {
  color: #E0F7FA;
  font-size: 13px;
}

.card {
  background-color: #16151E;
  border-radius: 16px;
  padding: 16px 18px;
  border: 1px solid rgba(91, 70, 246, 0.35);
}

.card-title {
  color: #FFFFFF;
  font-size: 14px;
  font-weight: 600;
}

.muted {
  color: #E0F7FA;
  font-size: 12px;
  opacity: 0.85;
}

.status {
  color: #FF9E00;
  font-size: 12px;
  font-weight: 600;
}

.chip {
  background-color: rgba(15, 14, 23, 0.55);
  border-radius: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(224, 247, 250, 0.12);
}

.chip-key {
  color: #FF7A00;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.4px;
}

.chip-desc {
  color: #FFFFFF;
  font-size: 12px;
}

button.accent {
  background-image: linear-gradient(90deg, #FF7A00, #FF9E00);
  background-color: #FF7A00;
  color: #0F0E17;
  border: none;
  border-radius: 12px;
  font-weight: 700;
  padding: 8px 14px;
}

button.accent:hover {
  background-image: linear-gradient(90deg, #FF9E00, #FF7A00);
}

button.ghost {
  background-color: #16151E;
  color: #E0F7FA;
  border: 1px solid rgba(91, 70, 246, 0.45);
  border-radius: 12px;
  padding: 8px 12px;
}

button.ghost:hover {
  border-color: #8F00FF;
  color: #FFFFFF;
}

switch {
  background-color: #0F0E17;
  border-radius: 16px;
  border: 1px solid rgba(224, 247, 250, 0.18);
  min-width: 48px;
  min-height: 26px;
}

switch:checked {
  background-image: linear-gradient(90deg, #5B46F6, #8F00FF);
  border-color: #8F00FF;
}

switch slider {
  background-color: #FFFFFF;
  border-radius: 13px;
  min-width: 22px;
  min-height: 22px;
  margin: 2px;
}

switch:checked slider {
  background-color: #E0F7FA;
}
"""


def hotkey_to_display(combo: str) -> str:
    names = {
        "<ctrl>": "CTRL",
        "<alt>": "ALT",
        "<shift>": "SHIFT",
        "<cmd>": "SUPER",
        "<super>": "SUPER",
    }
    parts = []
    for raw in combo.split("+"):
        token = raw.strip()
        if token in names:
            parts.append(names[token])
        elif token.startswith("<") and token.endswith(">"):
            parts.append(token[1:-1].upper())
        else:
            parts.append(token.upper())
    return " + ".join(parts)


def event_to_hotkey(event: Gdk.EventKey) -> str | None:
    name = Gdk.keyval_name(event.keyval)
    if not name or name in MODIFIER_KEYS:
        return None

    mods: list[str] = []
    state = Gdk.ModifierType(event.state)
    if state & Gdk.ModifierType.CONTROL_MASK:
        mods.append("<ctrl>")
    if state & Gdk.ModifierType.SHIFT_MASK:
        mods.append("<shift>")
    if state & Gdk.ModifierType.MOD1_MASK:
        mods.append("<alt>")
    if state & Gdk.ModifierType.SUPER_MASK:
        mods.append("<cmd>")

    key = Gdk.keyval_name(Gdk.keyval_to_lower(event.keyval)) or name
    key = key.lower()
    specials = {
        "return": "<enter>",
        "kp_enter": "<enter>",
        "escape": "<esc>",
        "space": "<space>",
        "tab": "<tab>",
        "backspace": "<backspace>",
        "delete": "<delete>",
        "plus": "<plus>",
        "minus": "-",
        "period": ".",
        "comma": ",",
    }
    if key in specials:
        key_token = specials[key]
    elif len(key) == 1:
        key_token = key
    elif key.startswith("f") and key[1:].isdigit():
        key_token = f"<{key}>"
    else:
        key_token = f"<{key}>"

    if not mods:
        return None
    return "+".join(mods + [key_token])


def load_config() -> tuple[str, str]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        save = str(data.get("save") or DEFAULT_SAVE)
        restore = str(data.get("restore") or DEFAULT_RESTORE)
        return save, restore
    except (OSError, json.JSONDecodeError, TypeError):
        return DEFAULT_SAVE, DEFAULT_RESTORE


def save_config(save: str, restore: str) -> None:
    CONFIG_PATH.write_text(
        json.dumps({"save": save, "restore": restore}, indent=2) + "\n",
        encoding="utf-8",
    )


class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, save: str, restore: str) -> None:
        super().__init__(title="Paramètres", transient_for=parent, modal=True)
        self.set_default_size(420, 280)
        self.set_border_width(16)
        self.save_hotkey = save
        self.restore_hotkey = restore
        self._capture: str | None = None

        box = self.get_content_area()
        box.set_spacing(14)
        box.set_margin_bottom(8)

        title = Gtk.Label(label="Raccourcis clavier")
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class("hero-title")
        box.pack_start(title, False, False, 0)

        hint = Gtk.Label(
            label="Cliquez sur Modifier, puis tapez la combinaison voulue."
        )
        hint.set_halign(Gtk.Align.START)
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("muted")
        box.pack_start(hint, False, False, 0)

        self.save_row, self.save_value = self._hotkey_row(
            "Sauvegarder la position", save, "save"
        )
        self.restore_row, self.restore_value = self._hotkey_row(
            "Restaurer la position", restore, "restore"
        )
        box.pack_start(self.save_row, False, False, 0)
        box.pack_start(self.restore_row, False, False, 0)

        self.capture_hint = Gtk.Label(label="")
        self.capture_hint.set_halign(Gtk.Align.START)
        self.capture_hint.get_style_context().add_class("status")
        box.pack_start(self.capture_hint, False, False, 0)

        close_btn = self.add_button("Fermer", Gtk.ResponseType.CLOSE)
        close_btn.get_style_context().add_class("accent")

        self.connect("key-press-event", self._on_key)
        self.show_all()

    def _hotkey_row(
        self, title: str, combo: str, which: str
    ) -> tuple[Gtk.Box, Gtk.Label]:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("card")

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name = Gtk.Label(label=title)
        name.set_halign(Gtk.Align.START)
        name.get_style_context().add_class("card-title")
        value = Gtk.Label(label=hotkey_to_display(combo))
        value.set_halign(Gtk.Align.START)
        value.get_style_context().add_class("chip-key")
        texts.pack_start(name, False, False, 0)
        texts.pack_start(value, False, False, 0)
        row.pack_start(texts, True, True, 0)

        button = Gtk.Button(label="Modifier")
        button.get_style_context().add_class("ghost")
        button.set_valign(Gtk.Align.CENTER)
        button.connect("clicked", self._start_capture, which)
        row.pack_end(button, False, False, 0)
        card.pack_start(row, False, False, 0)
        return card, value

    def _start_capture(self, _button: Gtk.Button, which: str) -> None:
        self._capture = which
        label = "sauvegarder" if which == "save" else "restaurer"
        self.capture_hint.set_text(f"Appuyez sur le raccourci pour {label}…")
        self.grab_focus()

    def _on_key(self, _widget, event: Gdk.EventKey) -> bool:
        if self._capture is None:
            return False
        if event.keyval == Gdk.KEY_Escape:
            self._capture = None
            self.capture_hint.set_text("Modification annulée.")
            return True
        combo = event_to_hotkey(event)
        if combo is None:
            return True
        other = self.restore_hotkey if self._capture == "save" else self.save_hotkey
        if combo == other:
            self.capture_hint.set_text("Ce raccourci est déjà utilisé.")
            return True
        if self._capture == "save":
            self.save_hotkey = combo
            self.save_value.set_text(hotkey_to_display(combo))
        else:
            self.restore_hotkey = combo
            self.restore_value.set_text(hotkey_to_display(combo))
        self.capture_hint.set_text(f"Enregistré : {hotkey_to_display(combo)}")
        self._capture = None
        return True


class MouseSaverApp(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="Sauvegarde souris")
        self.set_default_size(440, 380)
        self.set_resizable(False)
        self.set_border_width(18)
        self.connect("destroy", self._on_close)
        self._apply_css()

        self.mouse = Controller()
        self.saved_position: tuple[int, int] | None = None
        self._hotkeys: GlobalHotKeys | None = None
        self._lock = threading.Lock()
        self._enabled = True
        self.save_hotkey, self.restore_hotkey = load_config()

        self._build_ui()
        self._start_hotkeys()

    def _apply_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _label(self, text: str, css_class: str, wrap: bool = False) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.set_halign(Gtk.Align.START)
        label.set_xalign(0)
        label.get_style_context().add_class(css_class)
        if wrap:
            label.set_line_wrap(True)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        return label

    def _card(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("card")
        return box

    def _build_ui(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.add(root)

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hero.get_style_context().add_class("hero")
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        texts.pack_start(
            self._label("Position de la souris", "hero-title"), False, False, 0
        )
        texts.pack_start(
            self._label(
                "Enregistre et restaure le curseur — précision néon, fond studio.",
                "hero-sub",
                wrap=True,
            ),
            False,
            False,
            0,
        )
        hero.pack_start(texts, True, True, 0)

        settings_btn = Gtk.Button(label="Paramètres")
        settings_btn.get_style_context().add_class("accent")
        settings_btn.set_valign(Gtk.Align.CENTER)
        settings_btn.connect("clicked", self._open_settings)
        hero.pack_end(settings_btn, False, False, 0)
        root.pack_start(hero, False, False, 0)

        toggle_card = self._card()
        toggle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        toggle_texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        toggle_texts.pack_start(
            self._label("Raccourcis", "card-title"), False, False, 0
        )
        toggle_texts.pack_start(
            self._label("Active ou coupe l'écoute globale.", "muted"),
            False,
            False,
            0,
        )
        toggle_row.pack_start(toggle_texts, True, True, 0)

        self.toggle = Gtk.Switch()
        self.toggle.set_active(True)
        self.toggle.set_valign(Gtk.Align.CENTER)
        self.toggle.connect("notify::active", self._on_toggle)
        toggle_row.pack_end(self.toggle, False, False, 0)
        toggle_card.pack_start(toggle_row, False, False, 0)
        self.status_label = self._label(
            "Prêt — laissez cette fenêtre ouverte.", "status", wrap=True
        )
        toggle_card.pack_start(self.status_label, False, False, 0)
        root.pack_start(toggle_card, False, False, 0)

        shortcuts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        shortcuts.set_homogeneous(True)
        self.save_chip_key = self._label(
            hotkey_to_display(self.save_hotkey), "chip-key"
        )
        self.restore_chip_key = self._label(
            hotkey_to_display(self.restore_hotkey), "chip-key"
        )
        shortcuts.pack_start(
            self._shortcut_chip(self.save_chip_key, "Sauvegarder"), True, True, 0
        )
        shortcuts.pack_start(
            self._shortcut_chip(self.restore_chip_key, "Restaurer"), True, True, 0
        )
        root.pack_start(shortcuts, False, False, 0)

    def _shortcut_chip(self, key_label: Gtk.Label, desc: str) -> Gtk.Box:
        chip = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        chip.get_style_context().add_class("chip")
        chip.pack_start(key_label, False, False, 0)
        chip.pack_start(self._label(desc, "chip-desc"), False, False, 0)
        return chip

    def _refresh_shortcut_labels(self) -> None:
        self.save_chip_key.set_text(hotkey_to_display(self.save_hotkey))
        self.restore_chip_key.set_text(hotkey_to_display(self.restore_hotkey))

    def _open_settings(self, _button: Gtk.Button) -> None:
        was_enabled = self._enabled
        self._stop_hotkeys()
        dialog = SettingsDialog(self, self.save_hotkey, self.restore_hotkey)
        dialog.run()
        self.save_hotkey = dialog.save_hotkey
        self.restore_hotkey = dialog.restore_hotkey
        dialog.destroy()
        save_config(self.save_hotkey, self.restore_hotkey)
        self._refresh_shortcut_labels()
        if was_enabled:
            self._start_hotkeys()
            self._set_status("Raccourcis mis à jour.")
        else:
            self._set_status("Raccourcis enregistrés (écoute encore coupée).")

    def _on_toggle(self, switch: Gtk.Switch, _param) -> None:
        self._enabled = switch.get_active()
        if self._enabled:
            self._start_hotkeys()
            self._set_status("Raccourcis activés.")
        else:
            self._stop_hotkeys()
            self._set_status("Raccourcis désactivés.")

    def _start_hotkeys(self) -> None:
        self._stop_hotkeys()
        self._hotkeys = GlobalHotKeys(
            {
                self.save_hotkey: self._on_save,
                self.restore_hotkey: self._on_restore,
            }
        )
        self._hotkeys.start()

    def _stop_hotkeys(self) -> None:
        if self._hotkeys is not None:
            self._hotkeys.stop()
            self._hotkeys = None

    def _on_save(self) -> None:
        if not self._enabled:
            return
        with self._lock:
            x, y = self.mouse.position
            self.saved_position = (int(x), int(y))
        GLib.idle_add(self._set_status, "Position sauvegardée.")

    def _on_restore(self) -> None:
        if not self._enabled:
            return
        with self._lock:
            pos = self.saved_position
        if pos is None:
            GLib.idle_add(
                self._set_status,
                "Rien à restaurer : sauvegardez d'abord la position.",
            )
            return
        self.mouse.position = pos
        GLib.idle_add(self._set_status, "Souris ramenée à la position enregistrée.")

    def _set_status(self, message: str) -> bool:
        self.status_label.set_text(message)
        return False

    def _on_close(self, _widget) -> None:
        self._stop_hotkeys()
        Gtk.main_quit()


def main() -> None:
    app = MouseSaverApp()
    app.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
