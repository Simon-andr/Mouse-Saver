#!/usr/bin/env python3
"""Sauvegarde et restaure la position de la souris via raccourcis clavier."""

from __future__ import annotations

import os
import sys
import threading
import gi
from pathlib import Path

_VENV_PYTHON = Path(__file__).resolve().parent / ".venv" / "bin" / "python"





gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402
from pynput.keyboard import GlobalHotKeys  # noqa: E402
from pynput.mouse import Controller  # noqa: E402


class MouseSaverApp(Gtk.Window):
    SAVE_HOTKEY = "<ctrl>+<shift>+p"
    RESTORE_HOTKEY = "<ctrl>+<shift>+r"

    def __init__(self) -> None:
        super().__init__(title="Sauvegarde souris")
        self.set_default_size(420, 280)
        self.set_resizable(False)
        self.set_border_width(20)
        self.connect("destroy", self._on_close)

        self.mouse = Controller()
        self.saved_position: tuple[int, int] | None = None
        self._hotkeys: GlobalHotKeys | None = None
        self._lock = threading.Lock()
        self._enabled = True

        self._build_ui()
        self._start_hotkeys()

    def _build_ui(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(box)

        title = Gtk.Label(label="Position de la souris")
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class("title")
        box.pack_start(title, False, False, 0)

        subtitle = Gtk.Label(
            label="Enregistre et restaure le curseur avec des raccourcis."
        )
        subtitle.set_halign(Gtk.Align.START)
        subtitle.set_line_wrap(True)
        box.pack_start(subtitle, False, False, 0)

        self.toggle = Gtk.Switch()
        self.toggle.set_active(True)
        self.toggle.connect("notify::active", self._on_toggle)

        toggle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        toggle_label = Gtk.Label(label="Raccourcis activés")
        toggle_label.set_halign(Gtk.Align.START)
        toggle_row.pack_start(toggle_label, True, True, 0)
        toggle_row.pack_end(self.toggle, False, False, 0)
        box.pack_start(toggle_row, False, False, 8)

        self.position_label = Gtk.Label(label="Aucune position enregistrée")
        self.position_label.set_halign(Gtk.Align.START)
        self.position_label.set_selectable(True)
        box.pack_start(self.position_label, False, False, 0)

        self.status_label = Gtk.Label(
            label="Prêt — laissez cette fenêtre ouverte."
        )
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_line_wrap(True)
        box.pack_start(self.status_label, False, False, 0)

        help_label = Gtk.Label(
            label=(
                "Ctrl + Shift + P  →  sauvegarder la position\n"
                "Ctrl + Shift + R  →  y ramener la souris"
            )
        )
        help_label.set_halign(Gtk.Align.START)
        help_label.set_justify(Gtk.Justification.LEFT)
        box.pack_start(help_label, False, False, 8)

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
                self.SAVE_HOTKEY: self._on_save,
                self.RESTORE_HOTKEY: self._on_restore,
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
            pos = (int(x), int(y))
            self.saved_position = pos
        GLib.idle_add(self._update_saved_ui, pos[0], pos[1])

    def _on_restore(self) -> None:
        if not self._enabled:
            return
        with self._lock:
            pos = self.saved_position
        if pos is None:
            GLib.idle_add(
                self._set_status,
                "Rien à restaurer : sauvegardez d'abord avec Ctrl+Shift+P.",
            )
            return
        self.mouse.position = pos
        GLib.idle_add(
            self._set_status,
            f"Souris ramenée en ({pos[0]}, {pos[1]}).",
        )

    def _update_saved_ui(self, x: int, y: int) -> bool:
        self.position_label.set_text(f"Position enregistrée : ({x}, {y})")
        self._set_status("Position sauvegardée.")
        return False

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
