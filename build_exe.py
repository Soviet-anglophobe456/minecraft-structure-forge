"""Автоматическая сборка Minecraft Structure Forge в один Windows EXE.

Запуск из PowerShell или cmd:

    python build_exe.py

Скрипт намеренно использует отдельное окружение ``.venv-build``: зависимости
сборки не устанавливаются в глобальный Python пользователя.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import locale
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import List, Optional, Sequence


APP_NAME = "MinecraftStructureForge"
PYINSTALLER_REQUIREMENT = "PyInstaller==6.21.0"

PROJECT_DIR = Path(__file__).resolve().parent
MAIN_FILE = PROJECT_DIR / "main.py"
REQUIREMENTS_FILE = PROJECT_DIR / "requirements.txt"
VENV_DIR = PROJECT_DIR / ".venv-build"
HOOKS_DIR = PROJECT_DIR / ".pyinstaller-hooks"
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"
BUILD_LOG = PROJECT_DIR / "build_exe.log"
ROOT_EXE = PROJECT_DIR / (APP_NAME + ".exe")
ICON_FILE = PROJECT_DIR / "icon.ico"
INTERNAL_FLAG = "--_inside-build-venv"


class BuildError(RuntimeError):
    """Понятная пользователю ошибка подготовки или сборки приложения."""


def _configure_console() -> None:
    """Не даёт редким символам в выводе ломать старую Windows-консоль."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace", line_buffering=True, write_through=True)
            except (OSError, ValueError):
                pass


def _run(command: Sequence[str], description: str) -> None:
    """Запускает команду и превращает ненулевой код выхода в BuildError."""

    print("\n==> " + description)
    print("    " + subprocess.list2cmdline(list(command)))
    try:
        subprocess.run(list(command), cwd=str(PROJECT_DIR), check=True)
    except FileNotFoundError as exc:
        raise BuildError("Не удалось запустить команду: {}".format(command[0])) from exc
    except subprocess.CalledProcessError as exc:
        raise BuildError(
            "Команда завершилась с кодом {}: {}".format(
                exc.returncode, subprocess.list2cmdline(list(command))
            )
        ) from exc


def _run_pyinstaller(command: Sequence[str]) -> None:
    """Запускает PyInstaller, одновременно показывая и сохраняя его журнал."""

    print("\n==> Сборка одного EXE через PyInstaller")
    print("    " + subprocess.list2cmdline(list(command)))
    console_encoding = locale.getpreferredencoding(False) or "utf-8"
    try:
        with BUILD_LOG.open("w", encoding="utf-8", newline="") as log_file:
            process = subprocess.Popen(
                list(command),
                cwd=str(PROJECT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding=console_encoding,
                errors="replace",
            )
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="")
                log_file.write(line)
            return_code = process.wait()
    except OSError as exc:
        raise BuildError("Не удалось запустить PyInstaller: {}".format(exc)) from exc

    if return_code != 0:
        raise BuildError(
            "PyInstaller завершился с кодом {}. Подробности: {}".format(
                return_code, BUILD_LOG
            )
        )


def _venv_python() -> Path:
    """Возвращает путь к Python внутри окружения сборки."""

    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _check_project_files() -> None:
    """Проверяет обязательные входные файлы до установки пакетов."""

    missing = [path.name for path in (MAIN_FILE, REQUIREMENTS_FILE) if not path.is_file()]
    if missing:
        raise BuildError(
            "В папке проекта не найдены обязательные файлы: {}. "
            "Поместите build_exe.py рядом с main.py и requirements.txt.".format(
                ", ".join(missing)
            )
        )


def _create_or_update_venv(recreate: bool) -> Path:
    """Создаёт изолированное окружение и возвращает его python.exe."""

    if recreate and VENV_DIR.exists():
        # Удаляется только жёстко заданная папка окружения внутри проекта.
        if VENV_DIR.parent != PROJECT_DIR or VENV_DIR.name != ".venv-build":
            raise BuildError("Отказ от удаления неожиданного пути окружения.")
        print("==> Пересоздание окружения {}".format(VENV_DIR))
        shutil.rmtree(str(VENV_DIR))

    python_exe = _venv_python()
    if not python_exe.is_file():
        print("==> Создание виртуального окружения {}".format(VENV_DIR))
        try:
            venv.EnvBuilder(with_pip=True, clear=False).create(str(VENV_DIR))
        except Exception as exc:
            raise BuildError(
                "Не удалось создать виртуальное окружение: {}. "
                "Проверьте, что компонент venv установлен вместе с Python.".format(exc)
            ) from exc

    if not python_exe.is_file():
        raise BuildError("В окружении не найден Python: {}".format(python_exe))
    return python_exe


def _module_available(python_exe: Path, module_name: str) -> bool:
    """Проверяет импорт модуля именно в окружении сборки."""

    command = [
        str(python_exe),
        "-c",
        "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec({!r}) else 1)".format(
            module_name
        ),
    ]
    return subprocess.run(
        command,
        cwd=str(PROJECT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def _prepare_build_environment(python_exe: Path) -> None:
    """Устанавливает зависимости приложения и при необходимости PyInstaller."""

    _run(
        [
            str(python_exe),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(REQUIREMENTS_FILE),
        ],
        "Проверка и установка зависимостей из requirements.txt",
    )

    if _module_available(python_exe, "PyInstaller"):
        version_command = [
            str(python_exe),
            "-c",
            "import PyInstaller; print(PyInstaller.__version__)",
        ]
        print("\n==> PyInstaller уже установлен в окружении сборки")
        subprocess.run(version_command, cwd=str(PROJECT_DIR), check=False)
    else:
        _run(
            [
                str(python_exe),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                PYINSTALLER_REQUIREMENT,
            ],
            "Установка PyInstaller",
        )


def _verify_runtime_modules() -> None:
    """Даёт раннюю ошибку, если какая-либо зависимость не установилась."""

    required_modules = {
        "tkinter": "tkinter (компонент стандартной установки Python)",
        "nbtlib": "nbtlib",
        "PIL": "Pillow",
        "tkinterdnd2": "tkinterdnd2",
        "pyglet": "pyglet",
        "OpenGL": "PyOpenGL",
        "PyInstaller": "PyInstaller",
    }
    missing = [
        package
        for module, package in required_modules.items()
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        raise BuildError("Не установлены модули сборки: {}".format(", ".join(missing)))


def _write_tkinterdnd2_hook() -> Path:
    """Создаёт hook, который упаковывает Tcl-скрипты и DLL tkinterdnd2."""

    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    hook_file = HOOKS_DIR / "hook-tkinterdnd2.py"
    hook_text = '''"""Автоматически создан build_exe.py для PyInstaller."""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("tkinterdnd2")
hiddenimports = collect_submodules("tkinterdnd2")
'''
    hook_file.write_text(hook_text, encoding="utf-8")
    return hook_file


def _load_icon_font(size: int):
    """Выбирает жирный системный шрифт, сохраняя переносимость генератора."""

    from PIL import ImageFont

    windows_directory = Path(os.environ.get("WINDIR", "C:/Windows"))
    candidates = (
        windows_directory / "Fonts" / "arialbd.ttf",
        windows_directory / "Fonts" / "seguisb.ttf",
        Path("DejaVuSans-Bold.ttf"),
    )
    for font_path in candidates:
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_icon(icon_path: Path = ICON_FILE, overwrite: bool = False) -> Path:
    """Рисует яркий Minecraft-куб с монограммой SF и сохраняет ICO 16–256 px."""

    if icon_path.is_file() and not overwrite:
        print("==> Иконка уже существует: {}".format(icon_path))
        return icon_path

    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise BuildError(
            "Для генерации icon.ico нужен Pillow. Установите зависимости из requirements.txt."
        ) from exc

    # Рисуем в четырёхкратном разрешении, затем Pillow качественно уменьшает
    # изображение для каждого слоя ICO — так края остаются гладкими.
    scale = 4
    canvas_size = 256 * scale
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Тёмная скруглённая подложка хорошо читается и в Проводнике, и на панели задач.
    draw.rounded_rectangle(
        (34, 34, 990, 990),
        radius=210,
        fill="#0B1728",
        outline="#6EE7A8",
        width=26,
    )
    draw.rounded_rectangle((78, 78, 946, 946), radius=174, outline="#173A55", width=10)

    # Мягкая тень и три грани стилизованного строительного блока.
    draw.polygon(
        [(230, 384), (532, 200), (834, 384), (834, 704), (532, 888), (230, 704)],
        fill="#050B12",
    )
    top_face = [(210, 346), (512, 162), (814, 346), (512, 530)]
    left_face = [(210, 346), (512, 530), (512, 846), (210, 662)]
    right_face = [(512, 530), (814, 346), (814, 662), (512, 846)]
    draw.polygon(top_face, fill="#58D56B", outline="#07111E", width=24)
    draw.polygon(left_face, fill="#169B83", outline="#07111E", width=24)
    draw.polygon(right_face, fill="#2388E8", outline="#07111E", width=24)

    # Пиксельные блики напоминают травяной блок, не копируя игровые текстуры.
    for box, color in (
        ((334, 282, 386, 314), "#A0F278"),
        ((442, 220, 500, 254), "#2CBF68"),
        ((574, 262, 636, 296), "#8BE86E"),
        ((650, 326, 704, 358), "#24AD62"),
    ):
        draw.rounded_rectangle(box, radius=7, fill=color)

    # Белая монограмма остаётся различимой даже на уменьшенной иконке.
    font = _load_icon_font(258)
    label = "SF"
    text_box = draw.textbbox((0, 0), label, font=font, stroke_width=14)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    text_position = (
        (canvas_size - text_width) // 2 - text_box[0],
        590 - text_height // 2 - text_box[1],
    )
    draw.text(
        text_position,
        label,
        font=font,
        fill="#F7FBFF",
        stroke_width=18,
        stroke_fill="#07111E",
    )

    icon_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        image.save(
            str(icon_path),
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    except OSError as exc:
        raise BuildError("Не удалось сохранить {}: {}".format(icon_path, exc)) from exc

    if not icon_path.is_file() or icon_path.stat().st_size == 0:
        raise BuildError("Pillow не создал ожидаемый файл {}".format(icon_path))
    print("==> Иконка создана программно: {}".format(icon_path))
    return icon_path


def _build_command(python_exe: Path) -> List[str]:
    """Формирует воспроизводимую команду PyInstaller."""

    command = [
        str(python_exe),
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        "--name={}".format(APP_NAME),
        "--noconfirm",
        "--clean",
        "--additional-hooks-dir={}".format(HOOKS_DIR),
        # tkinterdnd2 хранит нативную DLL и Tcl-файлы внутри пакета.
        "--collect-all=tkinterdnd2",
        # Pyglet использует динамические импорты; PyOpenGL выбирает backend во время запуска.
        "--collect-all=pyglet",
        "--collect-submodules=OpenGL",
        "--hidden-import=PIL.ImageTk",
        # --icon встраивает значок в EXE, --add-data делает его доступным main.py.
        "--icon={}".format(ICON_FILE),
        "--add-data={}{}.".format(ICON_FILE, os.pathsep),
        "main.py",
    ]
    return command


def _copy_result_to_project_root() -> Path:
    """Атомарно копирует готовый EXE из dist в корень проекта."""

    source_exe = DIST_DIR / (APP_NAME + ".exe")
    if not source_exe.is_file() or source_exe.stat().st_size == 0:
        raise BuildError("PyInstaller не создал ожидаемый файл: {}".format(source_exe))

    temporary_target = PROJECT_DIR / ("." + APP_NAME + ".exe.tmp")
    try:
        shutil.copy2(str(source_exe), str(temporary_target))
        os.replace(str(temporary_target), str(ROOT_EXE))
    except PermissionError as exc:
        raise BuildError(
            "Не удалось заменить {}. Закройте уже запущенную программу и повторите сборку.".format(
                ROOT_EXE.name
            )
        ) from exc
    finally:
        if temporary_target.exists():
            temporary_target.unlink()
    return ROOT_EXE


def _sha256(path: Path) -> str:
    """Считает контрольную сумму, полезную при публикации релиза."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_inside_venv() -> None:
    """Выполняет непосредственно анализ модулей, упаковку и копирование."""

    expected_python = _venv_python().resolve()
    if Path(sys.executable).resolve() != expected_python:
        raise BuildError(
            "Внутренняя стадия запущена не из .venv-build: {}".format(sys.executable)
        )
    _verify_runtime_modules()
    generate_icon(ICON_FILE)
    hook_file = _write_tkinterdnd2_hook()
    print("==> Подготовлен hook для Drag & Drop: {}".format(hook_file))
    _run_pyinstaller(_build_command(expected_python))
    result = _copy_result_to_project_root()
    size_mib = result.stat().st_size / (1024 * 1024)
    print("\nСБОРКА ЗАВЕРШЕНА УСПЕШНО")
    print("EXE: {}".format(result))
    print("Размер: {:.1f} МиБ".format(size_mib))
    print("SHA-256: {}".format(_sha256(result)))
    print("Копия PyInstaller: {}".format(DIST_DIR / result.name))


def _parse_arguments(arguments: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Собрать Minecraft Structure Forge в один Windows EXE."
    )
    parser.add_argument(
        "--recreate-venv",
        action="store_true",
        help="удалить и заново создать только .venv-build перед сборкой",
    )
    parser.add_argument(INTERNAL_FLAG, action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(arguments)


def main(arguments: Optional[Sequence[str]] = None) -> int:
    _configure_console()
    options = _parse_arguments(arguments)
    try:
        if os.name != "nt":
            raise BuildError(
                "Windows EXE необходимо собирать на Windows: PyInstaller не выполняет кросс-компиляцию."
            )
        _check_project_files()
        if getattr(options, "_inside_build_venv"):
            _build_inside_venv()
            return 0

        python_exe = _create_or_update_venv(options.recreate_venv)
        _prepare_build_environment(python_exe)
        child_command = [str(python_exe), str(Path(__file__).resolve()), INTERNAL_FLAG]
        _run(child_command, "Запуск изолированной стадии сборки")
        return 0
    except BuildError as exc:
        print("\nОШИБКА СБОРКИ: {}".format(exc), file=sys.stderr)
        print("Подсказки по исправлению находятся в BUILD.md", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nСборка отменена пользователем.", file=sys.stderr)
        return 130
    except Exception as exc:
        print("\nНЕОЖИДАННАЯ ОШИБКА СБОРКИ: {}".format(exc), file=sys.stderr)
        print("Подробная инструкция находится в BUILD.md", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
