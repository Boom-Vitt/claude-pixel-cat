import os
import sys
import platform
import plistlib
import subprocess
from pathlib import Path


APP_ID = "com.local.pixelcat.desktoppet"
APP_NAME = "Pixel Cat"


def project_dir() -> Path:
    return Path(__file__).resolve().parent


def python_executable() -> Path:
    # Do NOT resolve(): in a venv the interpreter is a symlink to the base
    # Python, and resolving it points autostart at an interpreter without the
    # venv's packages (PySide6/Pillow), so the cat fails to launch at login.
    exe = Path(sys.executable)

    if platform.system() == "Windows":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            return pythonw

    return exe


def ensure_sprite_exists():
    root = project_dir()
    missing = []

    for name in ("cat-pixel1.png", "cat-pixel2.png"):
        if not (root / name).exists():
            missing.append(name)

    if missing:
        raise FileNotFoundError(
            "Missing sprite file(s): "
            + ", ".join(missing)
            + ". Put both PNG files in this project folder first."
        )


def install_macos():
    root = project_dir()
    py = python_executable()
    script = root / "pixel_cat.py"

    run_script = root / "run_pixel_cat.sh"
    run_script.write_text(
        f"""#!/bin/zsh
cd "{root}"
exec "{py}" "{script}"
""",
        encoding="utf-8",
    )
    run_script.chmod(0o755)

    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)

    plist_path = launch_agents / f"{APP_ID}.plist"

    plist_data = {
        "Label": APP_ID,
        "ProgramArguments": ["/bin/zsh", str(run_script)],
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(root / "pixel_cat.out.log"),
        "StandardErrorPath": str(root / "pixel_cat.err.log"),
        "WorkingDirectory": str(root),
    }

    with plist_path.open("wb") as f:
        plistlib.dump(plist_data, f)

    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    subprocess.run(["launchctl", "load", "-w", str(plist_path)], check=False)

    print("Installed macOS login startup:")
    print(plist_path)
    print()
    print("Pixel Cat will start automatically after user login.")
    print("To start it now, run:")
    print("python pixel_cat.py")


def install_windows():
    root = project_dir()
    py = python_executable()
    script = root / "pixel_cat.py"

    startup = (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )
    startup.mkdir(parents=True, exist_ok=True)

    bat_path = startup / "PixelCat.bat"

    bat_path.write_text(
        f"""@echo off
cd /d "{root}"
start "" "{py}" "{script}"
""",
        encoding="utf-8",
    )

    print("Installed Windows startup file:")
    print(bat_path)
    print()
    print("Pixel Cat will start automatically after user login.")
    print("To start it now, run:")
    print("python pixel_cat.py")


def main():
    ensure_sprite_exists()

    system = platform.system()

    if system == "Darwin":
        install_macos()
    elif system == "Windows":
        install_windows()
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


if __name__ == "__main__":
    main()
