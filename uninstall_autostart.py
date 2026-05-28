import os
import platform
import subprocess
from pathlib import Path


APP_ID = "com.local.pixelcat.desktoppet"


def uninstall_macos():
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"

    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink()
        print(f"Removed macOS LaunchAgent: {plist_path}")
    else:
        print("No macOS LaunchAgent found.")

    run_script = Path(__file__).resolve().parent / "run_pixel_cat.sh"
    if run_script.exists():
        run_script.unlink()
        print(f"Removed helper script: {run_script}")


def uninstall_windows():
    startup = (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )
    bat_path = startup / "PixelCat.bat"

    if bat_path.exists():
        bat_path.unlink()
        print(f"Removed Windows startup file: {bat_path}")
    else:
        print("No Windows startup file found.")


def main():
    system = platform.system()

    if system == "Darwin":
        uninstall_macos()
    elif system == "Windows":
        uninstall_windows()
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


if __name__ == "__main__":
    main()
