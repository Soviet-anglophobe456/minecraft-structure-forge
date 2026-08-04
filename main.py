"""Графический интерфейс конвертера Minecraft-схем."""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import math
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, Optional, Sequence, Tuple

from converter import (
    ConversionError,
    PreviewMap,
    RenderModel3D,
    StructureData,
    build_3d_render_model,
    build_preview_map,
    convert_file,
    load_schematic,
    load_structure_nbt,
    replace_blocks,
    rotate_structure,
)
from utils import STANDARD_BLOCK_NAMES, autocomplete_block_names

try:
    from PIL import Image, ImageTk
except ImportError:  # Понятная ошибка будет показана при попытке построить превью.
    Image = None
    ImageTk = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    BaseWindow = TkinterDnD.Tk
    DND_AVAILABLE = True
except ImportError:
    BaseWindow = tk.Tk
    DND_FILES = None
    DND_AVAILABLE = False


APP_VERSION = "v1.0.0"
TELEGRAM_URL = "https://t.me/+h2MuJGnEZYtmNDY0"


def resource_path(relative_path: str) -> Path:
    """Resolve a resource next to main.py or inside PyInstaller's _MEIPASS folder."""

    bundle_directory = getattr(sys, "_MEIPASS", None)
    base_directory = Path(bundle_directory) if bundle_directory else Path(__file__).resolve().parent
    return base_directory / relative_path


# Все пользовательские надписи хранятся централизованно. Интерфейс
# перестраивается при смене языка, поэтому перезапуск программы не требуется.
LANG: Dict[str, Dict[str, str]] = {
    "ru": {
        "window_title": "Minecraft Structure Forge {version}",
        "app_name": "Minecraft Structure Forge",
        "subtitle_dnd": "Перетащите файл в окно • WorldEdit / Sponge ↔ Java Structure NBT",
        "subtitle": "WorldEdit / Sponge Schematic ↔ Java Structure NBT",
        "mode_nbt": "SCHEMATIC  →  NBT",
        "mode_sponge": "NBT  →  SPONGE",
        "language": "Язык:",
        "check_updates": "Проверить обновления",
        "update_title": "Обновления",
        "update_current": "Установлена актуальная версия {version}.",
        "source": "Исходный файл",
        "choose_file": "📂  Выбрать файл",
        "drop_hint": "Можно бросить сюда .schematic, .schem или .nbt",
        "drop_missing": "Drag & Drop станет доступен после установки tkinterdnd2",
        "drop_unavailable": "Drag & Drop недоступен в этой сборке Tk",
        "output": "Папка сохранения",
        "folder": "📁  Папка",
        "transformations": "Преобразования",
        "optional": "необязательно",
        "replace": "Заменить блоки",
        "autocomplete": "Начните печатать — список отфильтруется автоматически",
        "rotation_y": "Поворот постройки вокруг оси Y",
        "convert": "⚡  КОНВЕРТИРОВАТЬ",
        "preview": "Интерактивное превью сверху",
        "open_3d": "◈  Открыть 3D",
        "rotation": "Поворот:",
        "zoom": "Масштаб:",
        "fit": "Вписать",
        "grid_none": "Сетка: —",
        "grid_value": "Сетка: {step} бл.",
        "preview_placeholder": "◇\n\nПеретащите или выберите схему\nдля построения карты",
        "preview_loading": "⌛\n\nЧитаем блоки…",
        "hover_default": "Наведите курсор на блок",
        "hover_help": "Колесо — масштаб • средняя кнопка — перемещение",
        "outside": "За границами постройки",
        "air": "x={x}  z={z}  •  воздух",
        "info": "Формат: {format}\nРазмер:  {width} × {height} × {length}\nБлоки:  {volume:,}   Палитра: {palette}\nТайлы:  {tiles}   Сущности: {entities}",
        "status_select": "Выберите или перетащите файл в окно",
        "status_analyzing": "Анализ файла и построение карты…",
        "status_loaded": "Файл загружен — можно конвертировать",
        "status_start": "Начинаем конвертацию…",
        "status_done": "Конвертация: {seconds:.2f} с  •  Сохранено: {filename}",
        "status_wait": "Дождитесь завершения текущей операции",
        "status_3d": "3D-просмотр открыт в отдельном окне",
        "status_drop_error": "Ошибка: перетащите файл .schematic, .schem или .nbt",
        "status_not_found": "Ошибка: файл не найден — {path}",
        "status_extension": "Ошибка: поддерживаются .schematic, .schem и .nbt",
        "status_output_missing": "Ошибка: папка сохранения не существует",
        "status_error": "Ошибка: {error}",
        "select_dialog": "Выберите схему или Structure NBT",
        "filetype_all": "Minecraft-схемы",
        "filetype_schematic": "WorldEdit / Sponge",
        "filetype_nbt": "Structure NBT",
        "filetype_any": "Все файлы",
        "output_dialog": "Выберите папку сохранения",
        "warning_title": "Не всё заполнено",
        "warning_fields": "Выберите исходный файл и папку сохранения.",
        "folder_title": "Папка не найдена",
        "folder_error": "Выбранная папка сохранения не существует.",
        "overwrite_title": "Файл уже существует",
        "overwrite": "Перезаписать файл?\n\n{path}",
        "replace_title": "Замена блоков",
        "replace_error": "Укажите исходный и новый блок.",
        "conversion_title": "Конвертация завершена",
        "saved": "Файл сохранён:\n{path}",
        "replaced": "\nЗаменено блоков: {count}",
        "warnings": "\n\nПредупреждения:\n• {warnings}",
        "format_error": "Ошибка формата",
        "error": "Ошибка",
        "3d_no_file": "Сначала загрузите постройку.",
        "3d_dependencies": "Для 3D-просмотра установите pyglet и PyOpenGL:\npython -m pip install -r requirements.txt",
        "3d_error_title": "Ошибка 3D-просмотра",
        "3d_caption": "3D-просмотр Minecraft — {shown}/{total} блоков{simplified} — {version}",
        "3d_simplified": " (упрощённый режим)",
        "3d_controls": "ПКМ: вращение • СКМ: панорама • колесо: масштаб • R: сброс • Esc: выход",
        "telegram": "Telegram: открыть канал",
        "author": "by gevihall ❤️",
    },
    "en": {
        "window_title": "Minecraft Structure Forge {version}",
        "app_name": "Minecraft Structure Forge",
        "subtitle_dnd": "Drop a file anywhere • WorldEdit / Sponge ↔ Java Structure NBT",
        "subtitle": "WorldEdit / Sponge Schematic ↔ Java Structure NBT",
        "mode_nbt": "SCHEMATIC  →  NBT",
        "mode_sponge": "NBT  →  SPONGE",
        "language": "Language:",
        "check_updates": "Check for updates",
        "update_title": "Updates",
        "update_current": "You are running the latest version, {version}.",
        "source": "Source file",
        "choose_file": "📂  Choose file",
        "drop_hint": "Drop a .schematic, .schem, or .nbt file here",
        "drop_missing": "Install tkinterdnd2 to enable Drag & Drop",
        "drop_unavailable": "Drag & Drop is unavailable in this Tk build",
        "output": "Output folder",
        "folder": "📁  Folder",
        "transformations": "Transformations",
        "optional": "optional",
        "replace": "Replace blocks",
        "autocomplete": "Start typing to filter the block list",
        "rotation_y": "Rotate structure around the Y axis",
        "convert": "⚡  CONVERT",
        "preview": "Interactive top preview",
        "open_3d": "◈  Open 3D",
        "rotation": "Rotation:",
        "zoom": "Zoom:",
        "fit": "Fit",
        "grid_none": "Grid: —",
        "grid_value": "Grid: {step} block(s)",
        "preview_placeholder": "◇\n\nDrop or choose a schematic\nto build the map",
        "preview_loading": "⌛\n\nReading blocks…",
        "hover_default": "Point at a block",
        "hover_help": "Wheel: zoom • middle button: pan",
        "outside": "Outside the structure",
        "air": "x={x}  z={z}  •  air",
        "info": "Format: {format}\nSize:    {width} × {height} × {length}\nBlocks:  {volume:,}   Palette: {palette}\nTiles:   {tiles}   Entities: {entities}",
        "status_select": "Choose or drop a file into the window",
        "status_analyzing": "Analyzing file and building map…",
        "status_loaded": "File loaded — ready to convert",
        "status_start": "Starting conversion…",
        "status_done": "Converted in {seconds:.2f} s  •  Saved as {filename}",
        "status_wait": "Wait for the current operation to finish",
        "status_3d": "3D viewer opened in a separate window",
        "status_drop_error": "Error: drop a .schematic, .schem, or .nbt file",
        "status_not_found": "Error: file not found — {path}",
        "status_extension": "Error: supported extensions are .schematic, .schem, and .nbt",
        "status_output_missing": "Error: output folder does not exist",
        "status_error": "Error: {error}",
        "select_dialog": "Choose a schematic or Structure NBT",
        "filetype_all": "Minecraft schematics",
        "filetype_schematic": "WorldEdit / Sponge",
        "filetype_nbt": "Structure NBT",
        "filetype_any": "All files",
        "output_dialog": "Choose output folder",
        "warning_title": "Missing information",
        "warning_fields": "Choose a source file and output folder.",
        "folder_title": "Folder not found",
        "folder_error": "The selected output folder does not exist.",
        "overwrite_title": "File already exists",
        "overwrite": "Overwrite this file?\n\n{path}",
        "replace_title": "Block replacement",
        "replace_error": "Enter both the source and replacement block.",
        "conversion_title": "Conversion complete",
        "saved": "File saved to:\n{path}",
        "replaced": "\nBlocks replaced: {count}",
        "warnings": "\n\nWarnings:\n• {warnings}",
        "format_error": "Format error",
        "error": "Error",
        "3d_no_file": "Load a structure first.",
        "3d_dependencies": "Install pyglet and PyOpenGL for the 3D viewer:\npython -m pip install -r requirements.txt",
        "3d_error_title": "3D viewer error",
        "3d_caption": "Minecraft 3D Viewer — {shown}/{total} blocks{simplified} — {version}",
        "3d_simplified": " (simplified mode)",
        "3d_controls": "Right drag: rotate • middle drag: pan • wheel: zoom • R: reset • Esc: close",
        "telegram": "Telegram: open channel",
        "author": "by gevihall ❤️",
    },
}


PROGRESS_EN = {
    "Открытие NBT…": "Opening NBT…",
    "Преобразование числовых ID…": "Converting numeric block IDs…",
    "Чтение палитры Sponge…": "Reading Sponge palette…",
    "Схема загружена": "Schematic loaded",
    "Открытие Structure NBT…": "Opening Structure NBT…",
    "Structure NBT загружена": "Structure NBT loaded",
    "Замена блоков…": "Replacing blocks…",
    "Формирование Structure NBT…": "Building Structure NBT…",
    "Готово": "Done",
}

FORMAT_EN = {
    "MCEdit / WorldEdit (классический)": "MCEdit / WorldEdit (classic)",
    "Minecraft Java Structure NBT": "Minecraft Java Structure NBT",
}


class SchematicConverterApp(BaseWindow):
    """Главное окно приложения."""

    COLORS: Dict[str, str] = {
        "bg": "#0b1119",
        "panel": "#111a25",
        "panel_alt": "#162231",
        "border": "#263548",
        "grid": "#314359",
        "grid_major": "#4a617d",
        "text": "#eaf1f8",
        "muted": "#8fa3b8",
        "accent": "#45c486",
        "accent_hover": "#63dda5",
        "blue": "#4ea1ff",
        "danger": "#ff6b6b",
        "entry": "#0e1721",
    }

    def __init__(self) -> None:
        super().__init__()
        self._lang_code = "ru"
        self.title(self._tr("window_title", version=APP_VERSION))
        self.geometry("1220x850")
        self.minsize(1040, 740)
        self.configure(bg=self.COLORS["bg"])
        self._window_icon_image: Optional[Any] = None
        self._header_logo_image: Optional[Any] = None
        self._set_window_icon()

        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.replace_var = tk.BooleanVar(value=False)
        self.replace_from_var = tk.StringVar(value="minecraft:stone")
        self.replace_to_var = tk.StringVar(value="minecraft:deepslate")
        self.rotation_var = tk.StringVar(value="0°")
        self.language_var = tk.StringVar(value="Русский")
        self.status_var = tk.StringVar(value=self._tr("status_select"))
        self.mode_var = tk.StringVar(value=self._tr("mode_nbt"))
        self.progress_var = tk.DoubleVar(value=0)
        self.zoom_var = tk.StringVar(value="—")
        self.grid_var = tk.StringVar(value=self._tr("grid_none"))
        self.hover_var = tk.StringVar(value=self._tr("hover_default"))

        self._events: "queue.Queue[tuple]" = queue.Queue()
        self._job_id = 0
        self._busy = False
        self._preview_photo: Optional[Any] = None
        self._preview_structure: Optional[StructureData] = None
        self._preview_map: Optional[PreviewMap] = None
        self._preview_zoom = 16.0
        self._preview_origin = (0.0, 0.0)
        self._extra_block_names: Tuple[str, ...] = ()
        self._fit_preview_after_resize = False
        self._dnd_root_configured = False

        self._configure_styles()
        self._build_ui()
        self._configure_drag_and_drop()
        self.rotation_var.trace_add("write", self._rotation_changed)
        self.after(80, self._poll_events)

    def _set_window_icon(self) -> None:
        """Set the window icon without failing when the bundled resource is unavailable."""

        icon_path = resource_path("icon.ico")
        if not icon_path.is_file():
            return

        # iconbitmap sets the native Windows title-bar and taskbar icon.
        try:
            self.iconbitmap(str(icon_path))
        except (OSError, tk.TclError):
            # Some non-Windows Tk builds cannot read ICO files via iconbitmap.
            pass

        # iconphoto is the cross-platform fallback. Keep a reference on the
        # window instance so Tk does not garbage-collect the PhotoImage.
        if Image is not None and ImageTk is not None:
            try:
                with Image.open(icon_path) as source_image:
                    rgba_icon = source_image.convert("RGBA")
                self._window_icon_image = ImageTk.PhotoImage(rgba_icon)
                self.iconphoto(True, self._window_icon_image)
            except (OSError, ValueError, tk.TclError):
                pass

    def _tr(self, key: str, **values: Any) -> str:
        """Возвращает локализованную строку с безопасным форматированием."""

        template = LANG.get(self._lang_code, LANG["ru"]).get(key, LANG["ru"].get(key, key))
        try:
            return template.format(**values)
        except (KeyError, ValueError):
            return template

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=self.COLORS["bg"])
        style.configure("Panel.TFrame", background=self.COLORS["panel"])
        style.configure("TLabel", background=self.COLORS["bg"], foreground=self.COLORS["text"], font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background=self.COLORS["panel"], foreground=self.COLORS["text"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=self.COLORS["panel"], foreground=self.COLORS["muted"], font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=self.COLORS["bg"], foreground=self.COLORS["text"], font=("Segoe UI Semibold", 22))
        style.configure("Subtitle.TLabel", background=self.COLORS["bg"], foreground=self.COLORS["muted"], font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=self.COLORS["panel"], foreground=self.COLORS["text"], font=("Segoe UI Semibold", 11))
        style.configure("Mode.TLabel", background="#17392e", foreground="#72e4ad", font=("Segoe UI Semibold", 9), padding=(10, 5))
        style.configure("TEntry", fieldbackground=self.COLORS["entry"], foreground=self.COLORS["text"], insertcolor=self.COLORS["text"], bordercolor=self.COLORS["border"], padding=8)
        style.map("TEntry", bordercolor=[("focus", self.COLORS["blue"])])
        style.configure("TCombobox", fieldbackground=self.COLORS["entry"], background=self.COLORS["panel_alt"], foreground=self.COLORS["text"], arrowcolor=self.COLORS["text"], padding=7)
        style.map("TCombobox", fieldbackground=[("readonly", self.COLORS["entry"])], foreground=[("readonly", self.COLORS["text"])])
        style.configure("TCheckbutton", background=self.COLORS["panel"], foreground=self.COLORS["text"], font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", self.COLORS["panel"])], indicatorcolor=[("selected", self.COLORS["accent"])])
        style.configure("Secondary.TButton", background=self.COLORS["panel_alt"], foreground=self.COLORS["text"], bordercolor=self.COLORS["border"], padding=(12, 8), font=("Segoe UI Semibold", 9))
        style.map("Secondary.TButton", background=[("active", "#203247"), ("disabled", "#111923")], foreground=[("disabled", "#607184")])
        style.configure("Tool.TButton", background=self.COLORS["panel_alt"], foreground=self.COLORS["text"], bordercolor=self.COLORS["border"], padding=(8, 5), font=("Segoe UI Semibold", 9))
        style.map("Tool.TButton", background=[("active", "#263a51")])
        style.configure("Green.Horizontal.TProgressbar", troughcolor=self.COLORS["entry"], background=self.COLORS["accent"], bordercolor=self.COLORS["entry"], lightcolor=self.COLORS["accent"], darkcolor=self.COLORS["accent"])

        # Цвет выпадающего списка Combobox задаётся через базу опций Tk.
        self.option_add("*TCombobox*Listbox.background", self.COLORS["entry"])
        self.option_add("*TCombobox*Listbox.foreground", self.COLORS["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", self.COLORS["blue"])

    def _build_ui(self) -> None:
        if hasattr(self, "_root_container") and self._root_container.winfo_exists():
            self._root_container.destroy()
        container = ttk.Frame(self, padding=(28, 16, 28, 10))
        self._root_container = container
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=5, uniform="content")
        container.columnconfigure(1, weight=4, uniform="content")
        container.rowconfigure(1, weight=1)

        header = ttk.Frame(container)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        header.columnconfigure(1, weight=1)
        self._create_logo(header).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        ttk.Label(header, text=self._tr("app_name"), style="Title.TLabel").grid(row=0, column=1, sticky="sw")
        dnd_text = self._tr("subtitle_dnd") if DND_AVAILABLE else self._tr("subtitle")
        ttk.Label(header, text=dnd_text, style="Subtitle.TLabel").grid(row=1, column=1, sticky="nw", pady=(2, 0))
        header_tools = ttk.Frame(header)
        header_tools.grid(row=0, column=2, rowspan=2, sticky="e")
        top_tools = ttk.Frame(header_tools)
        top_tools.pack(anchor="e")
        ttk.Label(top_tools, text=f"{APP_VERSION}", style="Subtitle.TLabel").pack(side="left", padx=(0, 8))
        ttk.Label(top_tools, textvariable=self.mode_var, style="Mode.TLabel").pack(side="left", padx=(0, 10))
        ttk.Label(top_tools, text=self._tr("language"), style="Subtitle.TLabel").pack(side="left", padx=(0, 5))
        self.language_box = ttk.Combobox(
            top_tools, textvariable=self.language_var, values=("Русский", "English"),
            state="readonly", width=10,
        )
        self.language_box.pack(side="left")
        self.language_box.bind("<<ComboboxSelected>>", self._change_language)
        ttk.Button(header_tools, text=self._tr("check_updates"), style="Tool.TButton", command=self._check_updates).pack(anchor="e", pady=(4, 0))

        controls = ttk.Frame(container, style="Panel.TFrame", padding=18)
        controls.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        controls.columnconfigure(0, weight=1)

        ttk.Label(controls, text=self._tr("source"), style="Section.TLabel").grid(row=0, column=0, sticky="w")
        file_row = ttk.Frame(controls, style="Panel.TFrame")
        file_row.grid(row=1, column=0, sticky="ew", pady=(6, 3))
        file_row.columnconfigure(0, weight=1)
        self.source_entry = ttk.Entry(file_row, textvariable=self.source_var, state="readonly")
        self.source_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.choose_button = ttk.Button(file_row, text=self._tr("choose_file"), style="Secondary.TButton", command=self._choose_file)
        self.choose_button.grid(row=0, column=1)
        dnd_hint = self._tr("drop_hint") if DND_AVAILABLE else self._tr("drop_missing")
        self.drop_hint_label = ttk.Label(controls, text=dnd_hint, style="Muted.TLabel")
        self.drop_hint_label.grid(row=2, column=0, sticky="w", pady=(2, 10))

        ttk.Label(controls, text=self._tr("output"), style="Section.TLabel").grid(row=3, column=0, sticky="w")
        output_row = ttk.Frame(controls, style="Panel.TFrame")
        output_row.grid(row=4, column=0, sticky="ew", pady=(6, 12))
        output_row.columnconfigure(0, weight=1)
        self.output_entry = ttk.Entry(output_row, textvariable=self.output_var, state="readonly")
        self.output_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.output_button = ttk.Button(output_row, text=self._tr("folder"), style="Secondary.TButton", command=self._choose_output)
        self.output_button.grid(row=0, column=1)

        tk.Frame(controls, height=1, bg=self.COLORS["border"]).grid(row=5, column=0, sticky="ew", pady=(1, 11))
        options_header = ttk.Frame(controls, style="Panel.TFrame")
        options_header.grid(row=6, column=0, sticky="ew")
        options_header.columnconfigure(0, weight=1)
        ttk.Label(options_header, text=self._tr("transformations"), style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(options_header, text=self._tr("optional"), style="Muted.TLabel").grid(row=0, column=1, sticky="e")

        replace_check = ttk.Checkbutton(controls, text=self._tr("replace"), variable=self.replace_var, command=self._toggle_replacement)
        replace_check.grid(row=7, column=0, sticky="w", pady=(9, 6))
        replacement_row = ttk.Frame(controls, style="Panel.TFrame")
        replacement_row.grid(row=8, column=0, sticky="ew")
        replacement_row.columnconfigure(0, weight=1)
        replacement_row.columnconfigure(2, weight=1)
        initial_values = STANDARD_BLOCK_NAMES[:200]
        self.replace_from = ttk.Combobox(replacement_row, textvariable=self.replace_from_var, values=initial_values, state="disabled")
        self.replace_from.grid(row=0, column=0, sticky="ew")
        ttk.Label(replacement_row, text="→", style="Panel.TLabel", font=("Segoe UI", 16)).grid(row=0, column=1, padx=10)
        self.replace_to = ttk.Combobox(replacement_row, textvariable=self.replace_to_var, values=initial_values, state="disabled")
        self.replace_to.grid(row=0, column=2, sticky="ew")
        for combo in (self.replace_from, self.replace_to):
            combo.bind("<KeyRelease>", lambda event, widget=combo: self._autocomplete_combo(widget, event))
            combo.bind("<<ComboboxSelected>>", lambda _event: self.focus_set())
        ttk.Label(controls, text=self._tr("autocomplete"), style="Muted.TLabel").grid(row=9, column=0, sticky="w", pady=(5, 10))

        rotation_row = ttk.Frame(controls, style="Panel.TFrame")
        rotation_row.grid(row=10, column=0, sticky="ew")
        rotation_row.columnconfigure(0, weight=1)
        ttk.Label(rotation_row, text=self._tr("rotation_y"), style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self.rotation_box = ttk.Combobox(rotation_row, textvariable=self.rotation_var, values=("0°", "90°", "180°", "270°"), state="readonly", width=10)
        self.rotation_box.grid(row=0, column=1, sticky="e")

        controls.rowconfigure(11, weight=1)
        self.progress = ttk.Progressbar(controls, variable=self.progress_var, maximum=100, style="Green.Horizontal.TProgressbar")
        self.progress.grid(row=12, column=0, sticky="ew", pady=(14, 5))
        self.status_label = tk.Label(
            controls, textvariable=self.status_var, bg=self.COLORS["panel"], fg=self.COLORS["muted"],
            anchor="w", justify="left", font=("Segoe UI", 9),
        )
        self.status_label.grid(row=13, column=0, sticky="ew")

        # Обычная tk.Button позволяет точно выделить кнопку цветом и задать
        # увеличенную высоту около 44 px независимо от выбранной ttk-темы.
        self.convert_button = tk.Button(
            controls, text=self._tr("convert"), command=self._start_conversion,
            bg="#285d47", activebackground=self.COLORS["accent_hover"], fg="#07140e",
            activeforeground="#07140e", disabledforeground="#91aa9e", relief="flat",
            bd=0, pady=8, font=("Segoe UI Semibold", 14), cursor="hand2", state="disabled",
        )
        self.convert_button.grid(row=14, column=0, sticky="ew", pady=(11, 0), ipady=2)
        self.convert_button.bind("<Enter>", self._convert_button_enter)
        self.convert_button.bind("<Leave>", self._convert_button_leave)

        self._build_preview_panel(container)

        # Футер остаётся видимым при растягивании окна.
        footer = ttk.Frame(container)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        footer.columnconfigure(1, weight=1)
        telegram = tk.Label(
            footer, text=self._tr("telegram"), bg=self.COLORS["bg"], fg=self.COLORS["blue"],
            cursor="hand2", font=("Segoe UI Semibold", 9),
        )
        telegram.grid(row=0, column=0, sticky="w")
        telegram.bind("<Button-1>", lambda _event: self._open_telegram())
        telegram.bind("<Enter>", lambda _event: telegram.configure(fg="#82bdff"))
        telegram.bind("<Leave>", lambda _event: telegram.configure(fg=self.COLORS["blue"]))
        tk.Label(
            footer, text=self._tr("author"), bg=self.COLORS["bg"], fg="#d6ad60",
            font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=2, sticky="e")

    def _build_preview_panel(self, parent: ttk.Frame) -> None:
        preview_panel = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        preview_panel.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        preview_panel.columnconfigure(0, weight=1)
        preview_panel.rowconfigure(3, weight=1)

        title_row = ttk.Frame(preview_panel, style="Panel.TFrame")
        title_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        title_row.columnconfigure(0, weight=1)
        ttk.Label(title_row, text=self._tr("preview"), style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.viewer_button = ttk.Button(title_row, text=self._tr("open_3d"), style="Tool.TButton", command=self._open_3d_viewer, state="disabled")
        self.viewer_button.grid(row=0, column=1, sticky="e", padx=(6, 8))
        ttk.Label(title_row, textvariable=self.grid_var, style="Muted.TLabel").grid(row=0, column=2, sticky="e")

        rotate_toolbar = ttk.Frame(preview_panel, style="Panel.TFrame")
        rotate_toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(rotate_toolbar, text=self._tr("rotation"), style="Muted.TLabel").pack(side="left", padx=(0, 6))
        for degrees in (0, 90, 180, 270):
            text = f"{degrees}°"
            ttk.Button(rotate_toolbar, text=text, style="Tool.TButton", command=lambda value=degrees: self._set_preview_rotation(value)).pack(side="left", padx=(0, 5))

        zoom_toolbar = ttk.Frame(preview_panel, style="Panel.TFrame")
        zoom_toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(zoom_toolbar, text=self._tr("zoom"), style="Muted.TLabel").pack(side="left", padx=(0, 6))
        ttk.Button(zoom_toolbar, text="−", style="Tool.TButton", width=3, command=lambda: self._change_zoom(1 / 1.25)).pack(side="left")
        ttk.Label(zoom_toolbar, textvariable=self.zoom_var, style="Panel.TLabel", width=9, anchor="center").pack(side="left", padx=4)
        ttk.Button(zoom_toolbar, text="+", style="Tool.TButton", width=3, command=lambda: self._change_zoom(1.25)).pack(side="left")
        ttk.Button(zoom_toolbar, text=self._tr("fit"), style="Tool.TButton", command=self._fit_preview).pack(side="left", padx=(7, 0))

        canvas_frame = ttk.Frame(preview_panel, style="Panel.TFrame")
        canvas_frame.grid(row=3, column=0, sticky="nsew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(
            canvas_frame, bg=self.COLORS["entry"], highlightbackground=self.COLORS["border"],
            highlightthickness=1, bd=0, cursor="crosshair",
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        x_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.preview_canvas.xview)
        y_scroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.preview_canvas.yview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.preview_canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.preview_canvas.create_text(
            200, 160, text=self._tr("preview_placeholder"),
            fill=self.COLORS["muted"], font=("Segoe UI", 11), justify="center", tags="placeholder",
        )
        self.preview_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.preview_canvas.bind("<Button-4>", self._on_mousewheel)
        self.preview_canvas.bind("<Button-5>", self._on_mousewheel)
        self.preview_canvas.bind("<Motion>", self._preview_motion)
        self.preview_canvas.bind("<Leave>", lambda _event: self.hover_var.set(self._tr("hover_default")))
        self.preview_canvas.bind("<ButtonPress-2>", lambda event: self.preview_canvas.scan_mark(event.x, event.y))
        self.preview_canvas.bind("<B2-Motion>", lambda event: self.preview_canvas.scan_dragto(event.x, event.y, gain=1))
        self.preview_canvas.bind("<Configure>", self._preview_canvas_resized)

        self.hover_label = tk.Label(
            preview_panel, textvariable=self.hover_var, justify="left", anchor="w",
            bg=self.COLORS["panel_alt"], fg=self.COLORS["text"], font=("Consolas", 9), padx=8, pady=6,
        )
        self.hover_label.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.info_var = tk.StringVar(value=self._tr(
            "info", format="—", width="—", height="—", length="—",
            volume=0, palette="—", tiles="—", entities="—",
        ))
        self.info_label = tk.Label(
            preview_panel, textvariable=self.info_var, justify="left", anchor="w",
            bg=self.COLORS["panel"], fg=self.COLORS["muted"], font=("Consolas", 9), pady=9,
        )
        self.info_label.grid(row=5, column=0, sticky="ew")

    def _create_logo(self, parent: ttk.Frame) -> tk.Label:
        """Display the same bundled SF icon in the application header."""

        icon_path = resource_path("icon.ico")
        if Image is not None and ImageTk is not None and icon_path.is_file():
            try:
                with Image.open(icon_path) as icon_source:
                    # Select a high-resolution ICO layer before resizing it for
                    # the header to preserve sharp edges.
                    if hasattr(icon_source, "ico") and (64, 64) in icon_source.ico.sizes():
                        logo_image = icon_source.ico.getimage((64, 64)).convert("RGBA")
                    else:
                        logo_image = icon_source.convert("RGBA")
                    resampling = getattr(Image, "Resampling", Image)
                    logo_image = logo_image.resize((58, 58), resampling.LANCZOS)
                self._header_logo_image = ImageTk.PhotoImage(logo_image)
                return tk.Label(
                    parent,
                    image=self._header_logo_image,
                    bg=self.COLORS["bg"],
                    bd=0,
                    highlightthickness=0,
                )
            except (OSError, ValueError, tk.TclError):
                pass

        # Keep the interface usable if the resource is corrupt or Pillow is missing.
        self._header_logo_image = None
        return tk.Label(
            parent,
            text="SF",
            width=4,
            height=2,
            bg=self.COLORS["bg"],
            fg=self.COLORS["accent"],
            font=("Segoe UI Black", 15),
            bd=0,
        )

    def _change_language(self, _event: Any = None) -> None:
        """Перестраивает все элементы интерфейса на выбранном языке."""

        new_language = "en" if self.language_var.get() == "English" else "ru"
        if new_language == self._lang_code:
            return
        self._lang_code = new_language
        self.title(self._tr("window_title", version=APP_VERSION))
        reverse = Path(self.source_var.get()).suffix.lower() == ".nbt" if self.source_var.get() else False
        self.mode_var.set(self._tr("mode_sponge" if reverse else "mode_nbt"))
        was_busy = self._busy
        self.grid_var.set(self._tr("grid_none"))
        self.hover_var.set(self._tr("hover_default"))
        self._build_ui()
        self._configure_drag_and_drop()
        if self._preview_structure is not None and self._preview_map is not None:
            self._show_preview(self._preview_structure, self._preview_map, fit=False)
            self._set_status(self._tr("status_wait" if was_busy else "status_loaded"), self.COLORS["blue"] if was_busy else self.COLORS["accent"])
        else:
            self._set_status(self._tr("status_wait" if was_busy else "status_select"), self.COLORS["blue"] if was_busy else self.COLORS["muted"])
        self._set_busy(was_busy)

    def _check_updates(self) -> None:
        """Локальная безопасная проверка версии без сетевого запроса."""

        messagebox.showinfo(
            self._tr("update_title"),
            self._tr("update_current", version=APP_VERSION),
            parent=self,
        )

    def _open_telegram(self) -> None:
        """Открывает Telegram-ссылку в системном браузере."""

        try:
            webbrowser.open(TELEGRAM_URL, new=2)
        except (OSError, webbrowser.Error) as exc:
            self._set_status(self._tr("status_error", error=exc), self.COLORS["danger"])

    def _open_3d_viewer(self) -> None:
        """Запускает независимое pyglet/OpenGL-окно, не блокируя tkinter."""

        source = Path(self.source_var.get()) if self.source_var.get() else None
        if source is None or not source.is_file():
            messagebox.showwarning(self._tr("3d_error_title"), self._tr("3d_no_file"), parent=self)
            return
        if importlib.util.find_spec("pyglet") is None or importlib.util.find_spec("OpenGL") is None:
            messagebox.showerror(self._tr("3d_error_title"), self._tr("3d_dependencies"), parent=self)
            return
        viewer_arguments = [
            "--viewer3d", str(source), "--rotation", str(self._rotation_degrees()),
            "--lang", self._lang_code,
        ]
        if getattr(sys, "frozen", False):
            # В one-file сборке 3D-окно запускается повторным вызовом самого EXE.
            # Переменная PyInstaller просит загрузчик создать независимый процесс,
            # а не считать его служебным дочерним экземпляром текущего приложения.
            command = [sys.executable, *viewer_arguments]
            working_directory = Path(sys.executable).resolve().parent
            child_environment = os.environ.copy()
            child_environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        else:
            command = [sys.executable, str(Path(__file__).resolve()), *viewer_arguments]
            working_directory = Path(__file__).resolve().parent
            child_environment = None
        if self.replace_var.get() and self.replace_from_var.get().strip() and self.replace_to_var.get().strip():
            command.extend(["--replace-from", self.replace_from_var.get().strip(), "--replace-to", self.replace_to_var.get().strip()])
        try:
            popen_options: Dict[str, Any] = {
                "cwd": str(working_directory),
                "env": child_environment,
            }
            if getattr(sys, "frozen", False):
                # У windowed-сборки нет консольных потоков; DEVNULL исключает
                # ошибки недействительных дескрипторов при запуске дочернего EXE.
                popen_options.update(
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            subprocess.Popen(command, **popen_options)
            self._set_status(self._tr("status_3d"), self.COLORS["accent"])
        except OSError as exc:
            self._set_status(self._tr("status_error", error=exc), self.COLORS["danger"])
            messagebox.showerror(self._tr("3d_error_title"), str(exc), parent=self)

    def _configure_drag_and_drop(self) -> None:
        """Регистрирует окно и Canvas как нативные цели Drag & Drop."""

        if not DND_AVAILABLE or DND_FILES is None:
            return
        try:
            widgets = [self.preview_canvas, self.source_entry]
            if not self._dnd_root_configured:
                widgets.append(self)
                self._dnd_root_configured = True
            for widget in widgets:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)
        except (tk.TclError, AttributeError):
            self.drop_hint_label.configure(text=self._tr("drop_unavailable"))

    def _on_drop(self, event: Any) -> str:
        """Получает список путей Tcl и загружает первый подходящий файл."""

        try:
            paths: Sequence[str] = self.tk.splitlist(event.data)
        except (tk.TclError, AttributeError):
            paths = (str(getattr(event, "data", "")).strip("{}"),)
        for raw_path in paths:
            candidate = Path(raw_path)
            if candidate.suffix.lower() in (".schematic", ".schem", ".nbt"):
                self._load_source_path(candidate)
                return "break"
        self._set_status(self._tr("status_drop_error"), self.COLORS["danger"])
        return "break"

    def _toggle_replacement(self) -> None:
        state = "normal" if self.replace_var.get() and not self._busy else "disabled"
        self.replace_from.configure(state=state)
        self.replace_to.configure(state=state)

    def _autocomplete_combo(self, combo: ttk.Combobox, event: Any) -> None:
        """Фильтрует список блоков после каждого введённого символа."""

        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab", "Shift_L", "Shift_R"):
            return
        suggestions = autocomplete_block_names(combo.get(), self._extra_block_names)
        combo.configure(values=suggestions)
        if suggestions and combo.get().strip():
            # ttk::combobox::Post открывает список без изменения текста поля.
            try:
                combo.tk.call("ttk::combobox::Post", str(combo))
            except tk.TclError:
                pass

    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title=self._tr("select_dialog"),
            filetypes=(
                (self._tr("filetype_all"), "*.schematic *.schem *.nbt"),
                (self._tr("filetype_schematic"), "*.schematic *.schem"),
                (self._tr("filetype_nbt"), "*.nbt"),
                (self._tr("filetype_any"), "*.*"),
            ),
        )
        if path:
            self._load_source_path(Path(path))

    def _load_source_path(self, source: Path) -> None:
        """Общий путь загрузки для диалога выбора и Drag & Drop."""

        if self._busy:
            self._set_status(self._tr("status_wait"), self.COLORS["danger"])
            return
        if not source.is_file():
            self._set_status(self._tr("status_not_found", path=source), self.COLORS["danger"])
            return
        if source.suffix.lower() not in (".schematic", ".schem", ".nbt"):
            self._set_status(self._tr("status_extension"), self.COLORS["danger"])
            return
        self.source_var.set(str(source))
        self.output_var.set(str(source.parent))
        reverse = source.suffix.lower() == ".nbt"
        self.mode_var.set(self._tr("mode_sponge" if reverse else "mode_nbt"))
        self._preview_structure = None
        self._preview_map = None
        self._start_preview(source)

    def _choose_output(self) -> None:
        initial = self.output_var.get() or str(Path.home())
        path = filedialog.askdirectory(title=self._tr("output_dialog"), initialdir=initial)
        if path:
            self.output_var.set(path)

    def _set_status(self, text: str, color: Optional[str] = None) -> None:
        self.status_var.set(text)
        self.status_label.configure(fg=color or self.COLORS["muted"])

    def _translate_progress(self, text: str) -> str:
        """Переводит сообщения converter.py для английского интерфейса."""

        if self._lang_code != "en":
            return text
        if text.startswith("Поворот на "):
            return text.replace("Поворот на ", "Rotating by ", 1)
        return PROGRESS_EN.get(text, text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.choose_button.configure(state="disabled" if busy else "normal")
        self.output_button.configure(state="disabled" if busy else "normal")
        self.rotation_box.configure(state="disabled" if busy else "readonly")
        self.viewer_button.configure(state="normal" if self.source_var.get() and not busy else "disabled")
        self._toggle_replacement()
        ready = bool(self.source_var.get()) and not busy
        self.convert_button.configure(
            state="normal" if ready else "disabled",
            bg=self.COLORS["accent"] if ready else "#285d47",
        )

    def _convert_button_enter(self, _event: Any) -> None:
        """Подсвечивает основную кнопку при наведении мыши."""

        if str(self.convert_button["state"]) == "normal":
            self.convert_button.configure(bg=self.COLORS["accent_hover"])

    def _convert_button_leave(self, _event: Any) -> None:
        if str(self.convert_button["state"]) == "normal":
            self.convert_button.configure(bg=self.COLORS["accent"])

    def _start_preview(self, source: Path) -> None:
        self._job_id += 1
        job_id = self._job_id
        self._set_busy(True)
        self.progress_var.set(0)
        self._set_status(self._tr("status_analyzing"), self.COLORS["blue"])
        self.preview_canvas.delete("all")
        self.preview_canvas.create_text(
            max(100, self.preview_canvas.winfo_width() // 2), max(80, self.preview_canvas.winfo_height() // 2),
            text=self._tr("preview_loading"), fill=self.COLORS["muted"],
            font=("Segoe UI", 11), justify="center", tags="placeholder",
        )

        def worker() -> None:
            try:
                callback = lambda value, text: self._events.put((job_id, "progress", value, text))
                structure = load_structure_nbt(source, callback) if source.suffix.lower() == ".nbt" else load_schematic(source, callback)
                preview = build_preview_map(structure)
                self._events.put((job_id, "preview_done", structure, preview))
            except Exception as exc:  # Ошибку покажет главный tkinter-поток.
                self._events.put((job_id, "error", exc))

        threading.Thread(target=worker, daemon=True, name="preview-loader").start()

    def _start_conversion(self) -> None:
        source_text = self.source_var.get()
        output_text = self.output_var.get()
        if not source_text or not output_text:
            messagebox.showwarning(self._tr("warning_title"), self._tr("warning_fields"), parent=self)
            return
        source = Path(source_text)
        output_dir = Path(output_text)
        if not output_dir.is_dir():
            self._set_status(self._tr("status_output_missing"), self.COLORS["danger"])
            messagebox.showerror(self._tr("folder_title"), self._tr("folder_error"), parent=self)
            return
        reverse = source.suffix.lower() == ".nbt"
        destination = output_dir / (f"{source.stem}_sponge.schem" if reverse else f"{source.stem}_structure.nbt")
        if destination.exists() and not messagebox.askyesno(
            self._tr("overwrite_title"), self._tr("overwrite", path=destination), parent=self,
        ):
            return
        replacement = None
        if self.replace_var.get():
            old, new = self.replace_from_var.get().strip(), self.replace_to_var.get().strip()
            if not old or not new:
                messagebox.showwarning(self._tr("replace_title"), self._tr("replace_error"), parent=self)
                return
            replacement = (old, new)
        rotation = int(self.rotation_var.get().rstrip("°"))

        self._job_id += 1
        job_id = self._job_id
        self._set_busy(True)
        self.progress_var.set(0)
        self._set_status(self._tr("status_start"), self.COLORS["blue"])

        def worker() -> None:
            try:
                started = time.perf_counter()
                callback = lambda value, text: self._events.put((job_id, "progress", value, text))
                result, structure, replacements = convert_file(source, destination, replacement, rotation, callback)
                elapsed = time.perf_counter() - started
                preview = build_preview_map(structure)
                self._events.put((job_id, "convert_done", result, structure, replacements, preview, elapsed))
            except Exception as exc:
                self._events.put((job_id, "error", exc))

        threading.Thread(target=worker, daemon=True, name="schematic-converter").start()

    def _poll_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                job_id, kind, *payload = event
                if job_id != self._job_id:
                    continue
                if kind == "progress":
                    self.progress_var.set(payload[0])
                    self._set_status(self._translate_progress(payload[1]), self.COLORS["blue"])
                elif kind == "preview_done":
                    structure, preview = payload
                    self._show_preview(structure, preview, fit=True)
                    self.progress_var.set(100)
                    self._set_status(self._tr("status_loaded"), self.COLORS["accent"])
                    self._set_busy(False)
                elif kind == "convert_done":
                    result, structure, replacements, preview, elapsed = payload
                    # Полученная structure уже повёрнута конвертером; сбрасываем
                    # настройку, чтобы не повернуть готовое превью второй раз.
                    self.rotation_var.set("0°")
                    self._show_preview(structure, preview, fit=True)
                    self.progress_var.set(100)
                    self._set_busy(False)
                    self._set_status(
                        self._tr("status_done", seconds=elapsed, filename=result.name),
                        self.COLORS["accent"],
                    )
                    replacement_text = self._tr("replaced", count=replacements) if self.replace_var.get() else ""
                    warning_text = ""
                    if structure.warnings:
                        warning_text = self._tr("warnings", warnings="\n• ".join(structure.warnings))
                    messagebox.showinfo(
                        self._tr("conversion_title"),
                        self._tr("saved", path=result) + replacement_text + warning_text,
                        parent=self,
                    )
                elif kind == "error":
                    self.progress_var.set(0)
                    self._set_busy(False)
                    error = payload[0]
                    self._set_status(self._tr("status_error", error=error), self.COLORS["danger"])
                    title = self._tr("format_error") if isinstance(error, (ConversionError, ValueError)) else self._tr("error")
                    messagebox.showerror(title, str(error), parent=self)
        except queue.Empty:
            pass
        self.after(80, self._poll_events)

    def _show_preview(self, structure: StructureData, preview: PreviewMap, fit: bool = False) -> None:
        self._preview_structure = structure
        self._preview_map = preview
        # Палитра выбранной схемы расширяет подсказки, включая модовые блоки.
        self._extra_block_names = tuple(sorted({block.name for block in structure.palette} | {block.as_string() for block in structure.palette}))
        source_format = FORMAT_EN.get(structure.source_format, structure.source_format) if self._lang_code == "en" else structure.source_format
        self.info_var.set(self._tr(
            "info", format=source_format, width=structure.width,
            height=structure.height, length=structure.length, volume=structure.volume,
            palette=len(structure.palette), tiles=len(structure.block_entities),
            entities=len(structure.entities),
        ))
        self.hover_var.set(self._tr("hover_help"))
        self._draw_preview(fit=fit)

    def _rotation_degrees(self) -> int:
        try:
            return int(self.rotation_var.get().rstrip("°")) % 360
        except ValueError:
            return 0

    def _set_preview_rotation(self, degrees: int) -> None:
        """Синхронно меняет поворот превью и будущей конвертации."""

        self.rotation_var.set(f"{degrees % 360}°")

    def _rotation_changed(self, *_args: Any) -> None:
        if self._preview_map is not None:
            self._draw_preview(fit=True)

    def _rotated_image(self) -> Any:
        if self._preview_map is None or Image is None:
            return None
        degrees = self._rotation_degrees()
        if degrees == 90:
            return self._preview_map.image.transpose(Image.Transpose.ROTATE_270)
        if degrees == 180:
            return self._preview_map.image.transpose(Image.Transpose.ROTATE_180)
        if degrees == 270:
            return self._preview_map.image.transpose(Image.Transpose.ROTATE_90)
        return self._preview_map.image

    @staticmethod
    def _nice_grid_step(zoom: float) -> int:
        """Выбирает шаг 1/2/5×10ⁿ так, чтобы линии не слипались."""

        minimum_blocks = max(1.0, 12.0 / max(0.01, zoom))
        exponent = 10 ** math.floor(math.log10(minimum_blocks))
        normalized = minimum_blocks / exponent
        multiplier = 1 if normalized <= 1 else 2 if normalized <= 2 else 5 if normalized <= 5 else 10
        return max(1, int(multiplier * exponent))

    def _draw_preview(self, fit: bool = False) -> None:
        """Масштабирует Pillow-карту, рисует её и адаптивную сетку на Canvas."""

        if self._preview_map is None or ImageTk is None or Image is None:
            return
        source_image = self._rotated_image()
        if source_image is None:
            return
        self.preview_canvas.update_idletasks()
        canvas_width = max(80, self.preview_canvas.winfo_width() - 2)
        canvas_height = max(80, self.preview_canvas.winfo_height() - 2)
        if fit:
            self._preview_zoom = max(0.25, min(48.0, min(canvas_width / source_image.width, canvas_height / source_image.height) * 0.92))
        self._preview_zoom = max(0.25, min(64.0, self._preview_zoom))

        # Ограничение защищает от огромного временного изображения при зуме.
        max_dimension = 12000
        if max(source_image.width, source_image.height) * self._preview_zoom > max_dimension:
            self._preview_zoom = max_dimension / max(source_image.width, source_image.height)
        target_width = max(1, int(round(source_image.width * self._preview_zoom)))
        target_height = max(1, int(round(source_image.height * self._preview_zoom)))
        scaled = source_image.resize((target_width, target_height), Image.Resampling.NEAREST)
        self._preview_photo = ImageTk.PhotoImage(scaled)

        self.preview_canvas.delete("all")
        origin_x = max(0.0, (canvas_width - target_width) / 2)
        origin_y = max(0.0, (canvas_height - target_height) / 2)
        self._preview_origin = (origin_x, origin_y)
        self.preview_canvas.create_image(origin_x, origin_y, image=self._preview_photo, anchor="nw", tags="map")

        grid_step = self._nice_grid_step(self._preview_zoom)
        self.grid_var.set(self._tr("grid_value", step=grid_step))
        grid_distance = grid_step * self._preview_zoom
        if grid_distance >= 6:
            columns, rows = source_image.width, source_image.height
            major_step = grid_step * 5
            for x in range(0, columns + 1, grid_step):
                px = origin_x + x * self._preview_zoom
                color = self.COLORS["grid_major"] if x % major_step == 0 else self.COLORS["grid"]
                self.preview_canvas.create_line(px, origin_y, px, origin_y + target_height, fill=color, width=1, tags="grid")
            for z in range(0, rows + 1, grid_step):
                py = origin_y + z * self._preview_zoom
                color = self.COLORS["grid_major"] if z % major_step == 0 else self.COLORS["grid"]
                self.preview_canvas.create_line(origin_x, py, origin_x + target_width, py, fill=color, width=1, tags="grid")

        scroll_width = max(canvas_width, origin_x + target_width)
        scroll_height = max(canvas_height, origin_y + target_height)
        self.preview_canvas.configure(scrollregion=(0, 0, scroll_width, scroll_height))
        if fit:
            self.preview_canvas.xview_moveto(0)
            self.preview_canvas.yview_moveto(0)
        self.zoom_var.set(f"{self._preview_zoom:.1f} px")

    def _change_zoom(self, factor: float) -> None:
        if self._preview_map is None:
            return
        x_fraction = self.preview_canvas.xview()[0]
        y_fraction = self.preview_canvas.yview()[0]
        self._preview_zoom *= factor
        self._draw_preview(fit=False)
        self.preview_canvas.xview_moveto(x_fraction)
        self.preview_canvas.yview_moveto(y_fraction)

    def _fit_preview(self) -> None:
        self._draw_preview(fit=True)

    def _on_mousewheel(self, event: Any) -> str:
        """Масштабирует карту колёсиком в Windows, macOS и Linux/X11."""

        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            self._change_zoom(1.18)
        elif getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            self._change_zoom(1 / 1.18)
        return "break"

    def _preview_canvas_resized(self, _event: Any) -> None:
        # Пока карта не загружена, центрируем текст-заглушку.
        if self._preview_map is None:
            self.preview_canvas.coords(
                "placeholder",
                max(100, self.preview_canvas.winfo_width() // 2),
                max(80, self.preview_canvas.winfo_height() // 2),
            )

    def _display_to_source(self, display_x: int, display_z: int) -> Tuple[int, int]:
        """Возвращает исходные X/Z после визуального поворота карты."""

        assert self._preview_map is not None
        width, length = self._preview_map.width, self._preview_map.length
        degrees = self._rotation_degrees()
        if degrees == 90:
            return display_z, length - 1 - display_x
        if degrees == 180:
            return width - 1 - display_x, length - 1 - display_z
        if degrees == 270:
            return width - 1 - display_z, display_x
        return display_x, display_z

    def _preview_motion(self, event: Any) -> None:
        """Показывает координаты, высоту и block state под курсором."""

        if self._preview_map is None:
            return
        canvas_x = self.preview_canvas.canvasx(event.x) - self._preview_origin[0]
        canvas_y = self.preview_canvas.canvasy(event.y) - self._preview_origin[1]
        display_x = int(canvas_x // self._preview_zoom)
        display_z = int(canvas_y // self._preview_zoom)
        source_x, source_z = self._display_to_source(display_x, display_z)
        if not (0 <= source_x < self._preview_map.width and 0 <= source_z < self._preview_map.length):
            self.hover_var.set(self._tr("outside"))
            return
        block, height = self._preview_map.block_at(source_x, source_z)
        if block is None:
            self.hover_var.set(self._tr("air", x=source_x, z=source_z))
            return
        self.hover_var.set(f"x={source_x}  y={height}  z={source_z}  •  {block.as_string()}")


def _build_3d_vertices(model: RenderModel3D) -> Tuple[list, int, int]:
    """Создаёт единый массив вершин; соседние внутренние грани пропускаются."""

    occupied = {(block.x, block.y, block.z) for block in model.blocks}
    vertices = []
    # normal, коэффициент света, четыре вершины грани относительно куба.
    faces = (
        ((0, 1, 0), 1.00, ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1))),
        ((0, -1, 0), 0.48, ((0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 0, 0))),
        ((0, 0, -1), 0.70, ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))),
        ((0, 0, 1), 0.86, ((1, 0, 1), (0, 0, 1), (0, 1, 1), (1, 1, 1))),
        ((-1, 0, 0), 0.62, ((0, 0, 1), (0, 0, 0), (0, 1, 0), (0, 1, 1))),
        ((1, 0, 0), 0.80, ((1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0))),
    )
    triangle_vertex_count = 0
    for block in model.blocks:
        for normal, shade, corners in faces:
            neighbor = (block.x + normal[0], block.y + normal[1], block.z + normal[2])
            if neighbor in occupied:
                continue
            color = tuple(max(0.0, min(1.0, channel * shade)) for channel in block.color)
            for corner_index in (0, 1, 2, 0, 2, 3):
                corner = corners[corner_index]
                vertices.extend((
                    block.x + corner[0], block.y + corner[1], block.z + corner[2],
                    color[0], color[1], color[2],
                ))
                triangle_vertex_count += 1

    # Сетка пола рисуется тем же VBO отдельным вызовом GL_LINES.
    grid_step = max(1, int(math.ceil(max(model.width, model.length) / 50)))
    grid_color = (0.20, 0.28, 0.38)
    line_vertex_count = 0
    for x in range(0, model.width + 1, grid_step):
        vertices.extend((x, -0.02, 0, *grid_color, x, -0.02, model.length, *grid_color))
        line_vertex_count += 2
    for z in range(0, model.length + 1, grid_step):
        vertices.extend((0, -0.02, z, *grid_color, model.width, -0.02, z, *grid_color))
        line_vertex_count += 2
    return vertices, triangle_vertex_count, line_vertex_count


def _run_pyglet_viewer(model: RenderModel3D, language: str) -> None:
    """Открывает аппаратно ускоренное OpenGL 3.3 окно с управлением камерой."""

    import numpy as np
    import pyglet
    from OpenGL.GL import (
        GL_ARRAY_BUFFER, GL_BLEND, GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT,
        GL_DEPTH_TEST, GL_FALSE, GL_FLOAT, GL_FRAGMENT_SHADER, GL_LINES,
        GL_ONE_MINUS_SRC_ALPHA, GL_SRC_ALPHA, GL_STATIC_DRAW, GL_TRIANGLES,
        GL_VERTEX_SHADER, glBindBuffer, glBindVertexArray, glBlendFunc,
        glBufferData, glClear, glClearColor, glDeleteBuffers, glDeleteProgram,
        glDeleteVertexArrays, glDisable, glDrawArrays, glEnable,
        glEnableVertexAttribArray, glGenBuffers, glGenVertexArrays, glGetUniformLocation,
        glLineWidth, glUniformMatrix4fv, glUseProgram, glVertexAttribPointer, glViewport,
    )
    from OpenGL.GL.shaders import compileProgram, compileShader
    from pyglet.window import key, mouse

    text = LANG.get(language, LANG["ru"])
    simplified_text = text["3d_simplified"] if model.simplified else ""
    caption = text["3d_caption"].format(
        shown=len(model.blocks), total=model.total_blocks,
        simplified=simplified_text, version=APP_VERSION,
    )
    try:
        config = pyglet.gl.Config(double_buffer=True, depth_size=24, major_version=3, minor_version=3)
        window = pyglet.window.Window(1100, 760, caption=caption, resizable=True, vsync=True, config=config)
    except Exception:
        # Драйвер может сам подобрать лучший совместимый контекст.
        window = pyglet.window.Window(1100, 760, caption=caption, resizable=True, vsync=True)

    vertex_shader = """
        #version 330 core
        layout(location = 0) in vec3 in_position;
        layout(location = 1) in vec3 in_color;
        uniform mat4 mvp;
        out vec3 vertex_color;
        void main() {
            gl_Position = mvp * vec4(in_position, 1.0);
            vertex_color = in_color;
        }
    """
    fragment_shader = """
        #version 330 core
        in vec3 vertex_color;
        out vec4 out_color;
        void main() {
            out_color = vec4(vertex_color, 1.0);
        }
    """
    shader = compileProgram(
        compileShader(vertex_shader, GL_VERTEX_SHADER),
        compileShader(fragment_shader, GL_FRAGMENT_SHADER),
    )
    mvp_location = glGetUniformLocation(shader, "mvp")
    raw_vertices, triangle_count, line_count = _build_3d_vertices(model)
    vertex_data = np.asarray(raw_vertices, dtype=np.float32)
    del raw_vertices

    vao = glGenVertexArrays(1)
    vbo = glGenBuffers(1)
    glBindVertexArray(vao)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, vertex_data.nbytes, vertex_data, GL_STATIC_DRAW)
    stride = 6 * vertex_data.itemsize
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
    glEnableVertexAttribArray(1)
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(3 * vertex_data.itemsize))
    glBindVertexArray(0)
    del vertex_data

    glEnable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glClearColor(0.035, 0.055, 0.08, 1.0)
    glLineWidth(1.0)

    center = np.array((model.width / 2, model.height / 2, model.length / 2), dtype=np.float32)
    maximum_size = max(1.0, float(max(model.width, model.height, model.length)))
    camera = {"yaw": -45.0, "pitch": 30.0, "distance": maximum_size * 1.9 + 5.0, "pan_x": 0.0, "pan_y": 0.0}

    def reset_camera() -> None:
        camera.update(yaw=-45.0, pitch=30.0, distance=maximum_size * 1.9 + 5.0, pan_x=0.0, pan_y=0.0)

    def translation(x: float, y: float, z: float) -> Any:
        matrix = np.identity(4, dtype=np.float32)
        matrix[:3, 3] = (x, y, z)
        return matrix

    def rotation_x(degrees: float) -> Any:
        angle = math.radians(degrees)
        cosine, sine = math.cos(angle), math.sin(angle)
        return np.array(((1, 0, 0, 0), (0, cosine, -sine, 0), (0, sine, cosine, 0), (0, 0, 0, 1)), dtype=np.float32)

    def rotation_y(degrees: float) -> Any:
        angle = math.radians(degrees)
        cosine, sine = math.cos(angle), math.sin(angle)
        return np.array(((cosine, 0, sine, 0), (0, 1, 0, 0), (-sine, 0, cosine, 0), (0, 0, 0, 1)), dtype=np.float32)

    def perspective(aspect: float) -> Any:
        near, far = 0.1, max(1000.0, camera["distance"] + maximum_size * 8)
        scale = 1.0 / math.tan(math.radians(55.0) / 2)
        matrix = np.zeros((4, 4), dtype=np.float32)
        matrix[0, 0] = scale / max(0.01, aspect)
        matrix[1, 1] = scale
        matrix[2, 2] = (far + near) / (near - far)
        matrix[2, 3] = (2 * far * near) / (near - far)
        matrix[3, 2] = -1
        return matrix

    controls_label = pyglet.text.Label(
        text["3d_controls"], x=12, y=12, anchor_x="left", anchor_y="bottom",
        color=(205, 219, 233, 230), font_size=10,
    )

    @window.event
    def on_draw() -> None:
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glViewport(0, 0, max(1, window.width), max(1, window.height))
        model_matrix = (
            translation(camera["pan_x"], camera["pan_y"], -camera["distance"])
            @ rotation_x(camera["pitch"])
            @ rotation_y(camera["yaw"])
            @ translation(-float(center[0]), -float(center[1]), -float(center[2]))
        )
        mvp = perspective(window.width / max(1, window.height)) @ model_matrix
        glUseProgram(shader)
        glUniformMatrix4fv(mvp_location, 1, GL_FALSE, np.ascontiguousarray(mvp.T))
        glBindVertexArray(vao)
        glDrawArrays(GL_TRIANGLES, 0, triangle_count)
        glDrawArrays(GL_LINES, triangle_count, line_count)
        glBindVertexArray(0)
        glUseProgram(0)
        glDisable(GL_DEPTH_TEST)
        controls_label.draw()
        glEnable(GL_DEPTH_TEST)

    @window.event
    def on_mouse_drag(_x: int, _y: int, dx: int, dy: int, buttons: int, _modifiers: int) -> None:
        if buttons & mouse.RIGHT:
            camera["yaw"] += dx * 0.45
            camera["pitch"] = max(-89.0, min(89.0, camera["pitch"] + dy * 0.45))
        if buttons & mouse.MIDDLE:
            factor = camera["distance"] / max(200.0, float(max(window.width, window.height))) * 1.8
            camera["pan_x"] += dx * factor
            camera["pan_y"] += dy * factor

    @window.event
    def on_mouse_scroll(_x: int, _y: int, _scroll_x: float, scroll_y: float) -> None:
        camera["distance"] *= 0.86 ** scroll_y
        camera["distance"] = max(maximum_size * 0.25, min(maximum_size * 25 + 100, camera["distance"]))

    @window.event
    def on_key_press(symbol: int, _modifiers: int) -> None:
        if symbol == key.ESCAPE:
            window.close()
        elif symbol == key.R:
            reset_camera()

    @window.event
    def on_close() -> None:
        try:
            glDeleteBuffers(1, [vbo])
            glDeleteVertexArrays(1, [vao])
            glDeleteProgram(shader)
        finally:
            pyglet.app.exit()

    pyglet.app.run()


def _show_viewer_error(language: str, error: Exception) -> None:
    """Показывает ошибку дочернего 3D-процесса в отдельном диалоге."""

    try:
        root = tk.Tk()
        root.withdraw()
        text = LANG.get(language, LANG["ru"])
        messagebox.showerror(text["3d_error_title"], str(error), parent=root)
        root.destroy()
    except Exception:
        # В headless Linux может отсутствовать графический DISPLAY.
        print(f"3D viewer error: {error}", file=sys.stderr)


def viewer_main(arguments: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--viewer3d", required=True)
    parser.add_argument("--rotation", type=int, default=0)
    parser.add_argument("--lang", choices=("ru", "en"), default="ru")
    parser.add_argument("--replace-from")
    parser.add_argument("--replace-to")
    options = parser.parse_args(arguments)
    try:
        source = Path(options.viewer3d)
        structure = load_structure_nbt(source) if source.suffix.lower() == ".nbt" else load_schematic(source)
        if options.replace_from and options.replace_to:
            structure, _count = replace_blocks(structure, options.replace_from, options.replace_to)
        if options.rotation:
            structure = rotate_structure(structure, options.rotation)
        model = build_3d_render_model(structure)
        _run_pyglet_viewer(model, options.lang)
    except Exception as exc:
        _show_viewer_error(options.lang, exc)


def main() -> None:
    app = SchematicConverterApp()
    app.mainloop()


if __name__ == "__main__":
    if "--viewer3d" in sys.argv:
        viewer_main()
    else:
        main()
