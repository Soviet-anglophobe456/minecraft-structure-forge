# Сборка Minecraft Structure Forge в один EXE

`build_exe.py` создаёт автономный `MinecraftStructureForge.exe`, который запускается без отдельной установки Python и Python-пакетов на целевом компьютере.

> PyInstaller не выполняет кросс-компиляцию. Windows-версию нужно собирать именно на Windows. Разрядность EXE совпадает с разрядностью Python, поэтому для обычного релиза рекомендуется 64-битный Python и Windows 10/11 x64.

## Автоматическая сборка

1. Установите Python 3.8 или новее с [python.org](https://www.python.org/downloads/windows/). В установщике включите **Add Python to PATH** и оставьте включёнными `pip`, `tkinter` и `venv`.
2. Откройте папку проекта в Проводнике. В адресной строке введите `powershell` и нажмите Enter. Это исключает распространённую ошибку запуска из `C:\Windows\System32`.
3. Выполните:

   ```powershell
   python build_exe.py
   ```

Скрипт автоматически:

- проверит наличие `main.py` и `requirements.txt`;
- создаст изолированное окружение `.venv-build`;
- установит в него зависимости из `requirements.txt`;
- проверит PyInstaller и установит его при отсутствии;
- создаст через Pillow многослойный `icon.ico`, если файл отсутствует;
- создаст hook для нативных файлов `tkinterdnd2`;
- выполнит эквивалент команды `pyinstaller --onefile --windowed --name="MinecraftStructureForge" main.py` с дополнительными параметрами для Drag & Drop, Pillow, pyglet и PyOpenGL;
- сохранит исходный результат в `dist\MinecraftStructureForge.exe` и скопирует его в корень проекта как `MinecraftStructureForge.exe`.

Во время повторных запусков окружение используется заново, а `pip install -r requirements.txt` безопасно проверяет, что его пакеты актуальны. Чтобы полностью пересоздать только окружение сборки:

```powershell
python build_exe.py --recreate-venv
```

## Проверка результата

После строки `СБОРКА ЗАВЕРШЕНА УСПЕШНО` запустите:

```powershell
.\MinecraftStructureForge.exe
```

Рекомендуется проверить выбор и перетаскивание `.schematic`, обычную конвертацию и отдельное окно 3D-просмотра. Для финальной проверки скопируйте EXE на чистый Windows-компьютер без Python.

Один EXE всё равно зависит от компонентов самой Windows и графического драйвера. 3D-окно требует рабочей поддержки OpenGL видеодрайвером.

## Ручная сборка

Если автоматический сценарий остановился, выполните команды по очереди из корня проекта:

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-build\Scripts\python.exe -m pip install PyInstaller==6.21.0
.\.venv-build\Scripts\python.exe -m PyInstaller --onefile --windowed --name MinecraftStructureForge --noconfirm --clean --icon icon.ico --add-data "icon.ico;." --collect-all tkinterdnd2 --collect-all pyglet --collect-submodules OpenGL --hidden-import PIL.ImageTk main.py
Copy-Item .\dist\MinecraftStructureForge.exe .\MinecraftStructureForge.exe -Force
```

Ручная команда использует `--collect-all tkinterdnd2` вместо создаваемого скриптом hook. Для релизной сборки предпочтителен `python build_exe.py`, потому что он применяет оба механизма и проверяет результат.

## Если сборка не удалась

Полный вывод PyInstaller записывается в `build_exe.log`.

- **`python` не найден.** Переустановите Python с опцией **Add Python to PATH** либо замените `python` в командах на `py -3`.
- **Нет `main.py` или `requirements.txt`.** Перейдите в папку проекта через `cd "полный\путь\к\проекту"`; не запускайте команды из `C:\Windows\System32`.
- **Не создаётся venv.** Проверьте компоненты `pip` и `venv` в установщике Python. Затем запустите `python build_exe.py --recreate-venv`.
- **Ошибка загрузки пакетов.** Проверьте интернет, прокси и сертификаты. Повторите установку командой `.\.venv-build\Scripts\python.exe -m pip install -r requirements.txt` — она покажет проблемный пакет.
- **`Permission denied` при копировании EXE.** Закройте запущенный `MinecraftStructureForge.exe`, окно 3D и повторите сборку.
- **Drag & Drop не работает.** Используйте автоматическую сборку: она добавляет Tcl-файлы и DLL `tkinterdnd2` через специальный hook.
- **3D-просмотр не открывается.** Обновите драйвер видеокарты. Если проблема только в сборке, найдите упоминания `pyglet` или `OpenGL` в `build_exe.log`.
- **Антивирус поместил EXE в карантин.** One-file приложения PyInstaller иногда эвристически проверяются строже. Не отключайте защиту; соберите файл на доверенной машине, проверьте его, опубликуйте SHA-256 и для публичного релиза подпишите EXE сертификатом code signing.
- **Сборка повреждена после обновлений.** Запустите `python build_exe.py --recreate-venv`, чтобы получить чистое окружение.

## Иконка приложения

Файл `icon.ico` создаётся функцией `generate_icon()` из `build_exe.py` с помощью Pillow. Он содержит слои 16, 24, 32, 48, 64, 128 и 256 пикселей. Если файл уже существует, сборщик сохраняет его без изменений; чтобы вернуть стандартный значок SF, удалите только `icon.ico` и снова выполните `python build_exe.py`.

Флаг `--icon=icon.ico` встраивает значок в Windows EXE, а `--add-data "icon.ico;."` помещает ICO внутрь one-file пакета, чтобы `main.py` мог установить его для заголовка окна.

## Что можно удалить после релиза

Каталоги `.venv-build`, `.pyinstaller-hooks`, `build`, `dist`, файл `MinecraftStructureForge.spec` и журнал `build_exe.log` относятся только к сборке. Готовому `MinecraftStructureForge.exe` они для запуска не нужны. Не удаляйте исходники, если планируете выпускать новые версии.
