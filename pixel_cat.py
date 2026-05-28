import os
import sys
import random
from pathlib import Path
from PIL import Image, ImageChops

from PySide6.QtCore import Qt, QTimer, QRect, QPoint
from PySide6.QtGui import (
    QPixmap,
    QImage,
    QPainter,
    QAction,
    QIcon,
    QPen,
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPolygon,
)
from PySide6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu


APP_NAME = "Pixel Cat"

WALK_SPRITE_FILE = "cat-pixel1.png"
SIT_SPRITE_FILE = "cat-pixel2.png"
# Mapped by what the art actually shows (the user's note had eat/poop swapped):
LIE_SPRITE_FILE = "cat-pixel3.png"   # lying on its back
EAT_SPRITE_FILE = "cat-pixel4.png"   # eating from a bowl
POOP_SPRITE_FILE = "cat-pixel5.png"  # in the litter box

CAT_DISPLAY_HEIGHT = int(os.environ.get("PIXEL_CAT_SIZE", "128"))
CAT_SPEED = float(os.environ.get("PIXEL_CAT_SPEED", "2.0"))
# Smoother: faster frame cycling (~90ms) and 60fps movement (~16ms).
ANIMATION_MS = int(os.environ.get("PIXEL_CAT_ANIMATION_MS", "90"))
MOVE_MS = int(os.environ.get("PIXEL_CAT_MOVE_MS", "16"))

AUTO_MODE_DEFAULT = os.environ.get("PIXEL_CAT_AUTO", "1") != "0"
WALK_DURATION_MS = int(os.environ.get("PIXEL_CAT_WALK_MS", "10000"))
SIT_DURATION_MS = int(os.environ.get("PIXEL_CAT_SIT_MS", "5000"))
LIE_DURATION_MS = int(os.environ.get("PIXEL_CAT_LIE_MS", "7000"))
EAT_DURATION_MS = int(os.environ.get("PIXEL_CAT_EAT_MS", "6000"))
POOP_DURATION_MS = int(os.environ.get("PIXEL_CAT_POOP_MS", "5000"))

# Every mode except "walk" is a stationary idle that animates in place.
STATIONARY_MODES = ("sit", "lie", "eat", "poop")
MODE_DURATIONS = {
    "walk": WALK_DURATION_MS,
    "sit": SIT_DURATION_MS,
    "lie": LIE_DURATION_MS,
    "eat": EAT_DURATION_MS,
    "poop": POOP_DURATION_MS,
}
# Auto-mode cycle: wander back to walking between activities.
AUTO_ORDER = ["walk", "sit", "walk", "lie", "walk", "eat", "walk", "poop"]

SPEECH_ENABLED = os.environ.get("PIXEL_CAT_SPEECH", "1") != "0"
SPEECH_INTERVAL_MS = int(os.environ.get("PIXEL_CAT_SPEECH_INTERVAL_MS", "5000"))
SPEECH_PHRASES = ["meow!", "nya~", "purr...", "hi!", "feed me?", "play?", "zzz..."]
CLICK_PHRASE = os.environ.get("PIXEL_CAT_CLICK_PHRASE", "play!")
CLICK_PAUSE_MS = int(os.environ.get("PIXEL_CAT_CLICK_PAUSE_MS", "1200"))

# Hiding the Dock icon (Accessory policy) makes the macOS Tool window invisible
# unless WA_MacAlwaysShowToolWindow is also set. Off by default so the cat is
# always visible; opt in with PIXEL_CAT_HIDE_DOCK=1.
HIDE_DOCK_ICON = os.environ.get("PIXEL_CAT_HIDE_DOCK", "0") != "0"


def resource_path(name: str) -> Path:
    return Path(__file__).resolve().parent / name


def hide_dock_icon_macos():
    """Run as a background accessory app on macOS: no Dock icon, no app switcher.

    There is no cross-platform Qt call for this, so we set the NSApplication
    activation policy to Accessory (1) via the Objective-C runtime with ctypes.
    The menu-bar (tray) status item still works under this policy.
    """
    if sys.platform != "darwin":
        return
    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        ns_app_class = objc.objc_getClass(b"NSApplication")

        objc.objc_msgSend.restype = ctypes.c_void_p
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        shared_app = objc.objc_msgSend(
            ns_app_class, objc.sel_registerName(b"sharedApplication")
        )

        # NSApplicationActivationPolicyAccessory == 1
        objc.objc_msgSend.restype = None
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
        objc.objc_msgSend(
            shared_app, objc.sel_registerName(b"setActivationPolicy:"), 1
        )
    except Exception:
        pass


def disable_window_shadow_macos(widget):
    """Remove the rectangular macOS drop-shadow from a frameless, translucent
    window. Without this, a box-shaped shadow appears behind the transparent
    cat. Must be called after the window is shown (so winId() is a real NSView).
    """
    if sys.platform != "darwin":
        return
    try:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        # ns_window = [ (NSView*)winId  window ]
        objc.objc_msgSend.restype = ctypes.c_void_p
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        ns_view = ctypes.c_void_p(int(widget.winId()))
        ns_window = objc.objc_msgSend(ns_view, objc.sel_registerName(b"window"))
        if not ns_window:
            return

        # [ns_window setHasShadow:NO]
        objc.objc_msgSend.restype = None
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        objc.objc_msgSend(ns_window, objc.sel_registerName(b"setHasShadow:"), False)

        # [ns_window invalidateShadow]
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        objc.objc_msgSend(ns_window, objc.sel_registerName(b"invalidateShadow"))
    except Exception:
        pass


def make_white_transparent(img: Image.Image) -> Image.Image:
    """Make near-white pixels (r, g, b all >= 245) fully transparent.

    Vectorized with PIL channel ops (no per-pixel Python loop) so loading
    several large sprite sheets at startup stays fast.
    """
    img = img.convert("RGBA")
    r, g, b, a = img.split()

    def near_white(channel):
        # 255 where the channel is >= 245, else 0
        return channel.point(lambda v: 255 if v >= 245 else 0)

    # mask == 255 only where ALL of r, g, b are near-white
    mask = ImageChops.multiply(
        ImageChops.multiply(near_white(r), near_white(g)), near_white(b)
    )
    # alpha becomes 0 where mask is 255 (near-white), unchanged elsewhere
    img.putalpha(ImageChops.subtract(a, mask))
    return img


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(
        data,
        img.width,
        img.height,
        img.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()
    return QPixmap.fromImage(qimg)


def load_sprite_frames(path: Path, frame_count: int = 4) -> list[QPixmap]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path.name}. Put {path.name} in the same folder as pixel_cat.py"
        )

    sheet = Image.open(path).convert("RGBA")
    sheet = make_white_transparent(sheet)

    frame_w = sheet.width // frame_count
    frame_h = sheet.height

    if frame_w <= 0 or frame_h <= 0:
        raise ValueError(f"{path.name} has invalid dimensions.")

    frames = []

    for i in range(frame_count):
        crop = sheet.crop((i * frame_w, 0, (i + 1) * frame_w, frame_h))
        frames.append(pil_to_qpixmap(crop))

    return frames


class PixelCatWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.frames_by_mode = {
            "walk": load_sprite_frames(resource_path(WALK_SPRITE_FILE), 4),
            "sit": load_sprite_frames(resource_path(SIT_SPRITE_FILE), 4),
            "lie": load_sprite_frames(resource_path(LIE_SPRITE_FILE), 4),
            "eat": load_sprite_frames(resource_path(EAT_SPRITE_FILE), 4),
            "poop": load_sprite_frames(resource_path(POOP_SPRITE_FILE), 4),
        }
        self.walk_frames = self.frames_by_mode["walk"]
        self.sit_frames = self.frames_by_mode["sit"]

        self.mode = "walk"
        self.auto_mode = AUTO_MODE_DEFAULT
        self.auto_index = 0
        self.frame_index = 0
        self.frame_dir = 1
        self.facing_left = True

        first = self.walk_frames[0]
        self.sprite_w = first.width()
        self.sprite_h = first.height()

        scale = CAT_DISPLAY_HEIGHT / max(1, self.sprite_h)
        self.display_w = int(self.sprite_w * scale)
        self.display_h = int(CAT_DISPLAY_HEIGHT)

        # Reserve a zone above the cat for a "talking" speech bubble. The window
        # only grows upward; the cat still occupies the bottom display_h, so the
        # horizontal movement/bounce math (which uses display_w) stays unchanged.
        self.bubble_font = QFont()
        self.bubble_font.setBold(True)
        self.bubble_font.setPixelSize(max(11, int(self.display_h * 0.13)))
        metrics = QFontMetrics(self.bubble_font)
        self.bubble_pad = max(6, int(self.display_h * 0.05))
        self.bubble_tail_h = max(6, int(self.display_h * 0.06))
        self.bubble_text_h = metrics.height()
        self.bubble_zone_h = self.bubble_text_h + self.bubble_pad * 2 + self.bubble_tail_h + 6
        self.cat_top = self.bubble_zone_h
        self.window_h = self.display_h + self.bubble_zone_h

        self.speaking = SPEECH_ENABLED
        self.speech_text = SPEECH_PHRASES[0] if SPEECH_ENABLED else ""
        self.click_pause = False
        self._first_paint_logged = False

        self.x = 0.0
        self.y = 0.0
        self.vx = -abs(CAT_SPEED)

        self.setFixedSize(self.display_w, self.window_h)

        # NOTE: do NOT add Qt.WindowType.NoDropShadowWindowHint here. On macOS it
        # blanks this translucent, frameless window (the cat disappears). The
        # window's drop-shadow is removed instead via disable_window_shadow_macos()
        # (native NSWindow.setHasShadow:NO), which does not affect visibility.
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        # The window is intentionally NOT click-through, so that clicking the
        # cat can pop a "play!" bubble. Trade-off: the small cat+bubble window
        # area now captures clicks instead of passing them through to whatever
        # is behind it.
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        if HIDE_DOCK_ICON and hasattr(Qt.WidgetAttribute, "WA_MacAlwaysShowToolWindow"):
            # A Tool window hides when the app is inactive; an Accessory (no-Dock)
            # app is never active, so force the tool window to stay visible.
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)

        self.setWindowTitle(APP_NAME)

        self.place_near_bottom_right()

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.next_frame)
        self.anim_timer.start(ANIMATION_MS)

        self.move_timer = QTimer(self)
        self.move_timer.timeout.connect(self.move_cat)
        self.move_timer.start(MOVE_MS)

        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)
        self.auto_timer.timeout.connect(self.auto_switch_mode)

        if self.auto_mode:
            self.auto_timer.start(WALK_DURATION_MS)

        self.speak_timer = QTimer(self)
        self.speak_timer.timeout.connect(self.speak)

        self.click_pause_timer = QTimer(self)
        self.click_pause_timer.setSingleShot(True)
        self.click_pause_timer.timeout.connect(self.end_click_pause)

        if SPEECH_ENABLED:
            self.speak_timer.start(SPEECH_INTERVAL_MS)

    def active_frames(self) -> list[QPixmap]:
        return self.frames_by_mode.get(self.mode, self.walk_frames)

    def current_screen_rect(self):
        screen = QApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QApplication.primaryScreen()
        return screen.availableGeometry()

    def place_near_bottom_right(self):
        geo = QApplication.primaryScreen().availableGeometry()
        self.x = geo.right() - self.display_w - 40
        self.y = geo.bottom() - self.window_h - 40
        self.move(int(self.x), int(self.y))

    def next_frame(self):
        frames = self.active_frames()
        n = len(frames)
        if self.mode == "walk":
            # Looping walk cycle.
            self.frame_index = (self.frame_index + 1) % n
        else:
            # Ping-pong idle (0,1,2,3,2,1,...) — smoother than a hard loop
            # because it never snaps from the last frame back to the first.
            self.frame_index += self.frame_dir
            if self.frame_index >= n - 1:
                self.frame_index = n - 1
                self.frame_dir = -1
            elif self.frame_index <= 0:
                self.frame_index = 0
                self.frame_dir = 1
        self.update()

    def move_cat(self):
        if self.mode != "walk":
            return

        if self.click_pause:
            return

        geo = self.current_screen_rect()
        self.x += self.vx

        if self.x <= geo.left():
            self.x = geo.left()
            self.vx = abs(self.vx)
            self.facing_left = False

        if self.x + self.display_w >= geo.right():
            self.x = geo.right() - self.display_w
            self.vx = -abs(self.vx)
            self.facing_left = True

        self.move(int(self.x), int(self.y))

    def set_mode(self, mode: str):
        if mode not in MODE_DURATIONS:
            return

        self.mode = mode
        self.frame_index = 0
        self.frame_dir = 1

        if mode in STATIONARY_MODES:
            self.snap_to_bottom()
        else:
            self.facing_left = self.vx < 0

        self.update()

        if self.auto_mode:
            self.restart_auto_timer()

    def snap_to_bottom(self):
        geo = self.current_screen_rect()
        self.y = geo.bottom() - self.window_h - 40

        if self.x < geo.left():
            self.x = geo.left()

        if self.x + self.display_w > geo.right():
            self.x = geo.right() - self.display_w

        self.move(int(self.x), int(self.y))

    def toggle_auto_mode(self):
        self.auto_mode = not self.auto_mode

        if self.auto_mode:
            self.restart_auto_timer()
        else:
            self.auto_timer.stop()

    def restart_auto_timer(self):
        self.auto_timer.stop()
        self.auto_timer.start(MODE_DURATIONS.get(self.mode, SIT_DURATION_MS))

    def auto_switch_mode(self):
        if not self.auto_mode:
            return

        self.auto_index = (self.auto_index + 1) % len(AUTO_ORDER)
        self.set_mode(AUTO_ORDER[self.auto_index])

    def speak(self):
        # Cycle the phrase; the bubble stays visible at all times (always-on).
        if not SPEECH_ENABLED:
            return
        self.speech_text = random.choice(SPEECH_PHRASES)
        self.speaking = True
        self.update()

    def say(self, text):
        # Show a specific phrase right now (used when the cat is clicked).
        self.speech_text = text
        self.speaking = True
        self.update()
        if SPEECH_ENABLED:
            # Keep this phrase up for a full cycle before resuming random ones.
            self.speak_timer.start(SPEECH_INTERVAL_MS)

    def end_click_pause(self):
        self.click_pause = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.say(CLICK_PHRASE)
            # Briefly stop walking so the "play!" bubble is readable.
            self.click_pause = True
            self.click_pause_timer.start(CLICK_PAUSE_MS)
            event.accept()

    def draw_speech_bubble(self, painter):
        metrics = QFontMetrics(self.bubble_font)
        text = self.speech_text
        text_w = metrics.horizontalAdvance(text)
        bubble_w = min(self.display_w - 4, text_w + self.bubble_pad * 2)
        bubble_h = self.bubble_text_h + self.bubble_pad * 2
        bubble_x = (self.display_w - bubble_w) // 2
        bubble_y = 3

        painter.setPen(QPen(QColor(0, 0, 0), 2))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        radius = max(4, bubble_h // 3)
        painter.drawRoundedRect(bubble_x, bubble_y, bubble_w, bubble_h, radius, radius)

        center_x = self.display_w // 2
        tail_top = bubble_y + bubble_h
        tail = QPolygon([
            QPoint(center_x - 6, tail_top - 2),
            QPoint(center_x + 6, tail_top - 2),
            QPoint(center_x, tail_top + self.bubble_tail_h),
        ])
        painter.drawPolygon(tail)

        painter.setPen(QColor(0, 0, 0))
        painter.setFont(self.bubble_font)
        painter.drawText(
            QRect(bubble_x, bubble_y, bubble_w, bubble_h),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)

        frames = self.active_frames()
        pixmap = frames[self.frame_index % len(frames)]

        # Preserve each sprite's aspect ratio (some sheets, e.g. the litter box,
        # are taller than wide). Fit inside the cat area, bottom-aligned and
        # horizontally centered, so no pose ever looks squished.
        fw = max(1, pixmap.width())
        fh = max(1, pixmap.height())
        fit = min(self.display_w / fw, self.display_h / fh)
        tw = max(1, int(fw * fit))
        th = max(1, int(fh * fit))
        tx = (self.display_w - tw) // 2
        ty = self.cat_top + (self.display_h - th)
        target = QRect(tx, ty, tw, th)

        painter.save()
        if self.mode == "walk" and not self.facing_left:
            painter.translate(self.display_w, 0)
            painter.scale(-1, 1)
        painter.drawPixmap(target, pixmap, pixmap.rect())
        painter.restore()

        if self.speaking and self.speech_text:
            self.draw_speech_bubble(painter)

        if not self._first_paint_logged:
            self._first_paint_logged = True
            print("pixel-cat: window painted", flush=True)


class PixelCatApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName(APP_NAME)
        self.app.setQuitOnLastWindowClosed(False)

        self.window = PixelCatWindow()
        self.window.show()

        # Kill the rectangular macOS window shadow behind the transparent cat.
        # Re-applied via the event loop too, since the shadow can be recreated.
        disable_window_shadow_macos(self.window)
        QTimer.singleShot(0, lambda: disable_window_shadow_macos(self.window))

        if HIDE_DOCK_ICON:
            # Become a background accessory app (no Dock icon). Scheduled via the
            # event loop too, in case Qt resets the policy during startup.
            hide_dock_icon_macos()
            QTimer.singleShot(0, hide_dock_icon_macos)

        self.tray = QSystemTrayIcon()
        self.tray.setToolTip(APP_NAME)

        if self.window.walk_frames:
            self.tray.setIcon(QIcon(self.window.walk_frames[0]))

        self.menu = QMenu()

        self.walk_action = QAction("Walk")
        self.walk_action.triggered.connect(lambda: self.window.set_mode("walk"))
        self.menu.addAction(self.walk_action)

        self.sit_action = QAction("Sit")
        self.sit_action.triggered.connect(lambda: self.window.set_mode("sit"))
        self.menu.addAction(self.sit_action)

        self.lie_action = QAction("Lie Down")
        self.lie_action.triggered.connect(lambda: self.window.set_mode("lie"))
        self.menu.addAction(self.lie_action)

        self.eat_action = QAction("Eat")
        self.eat_action.triggered.connect(lambda: self.window.set_mode("eat"))
        self.menu.addAction(self.eat_action)

        self.poop_action = QAction("Poop")
        self.poop_action.triggered.connect(lambda: self.window.set_mode("poop"))
        self.menu.addAction(self.poop_action)

        self.menu.addSeparator()

        self.auto_action = QAction("Auto Mode: ON" if self.window.auto_mode else "Auto Mode: OFF")
        self.auto_action.triggered.connect(self.toggle_auto_mode)
        self.menu.addAction(self.auto_action)

        self.menu.addSeparator()

        quit_action = QAction("Quit Pixel Cat")
        quit_action.triggered.connect(self.quit)
        self.menu.addAction(quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.show()

    def toggle_auto_mode(self):
        self.window.toggle_auto_mode()
        self.auto_action.setText("Auto Mode: ON" if self.window.auto_mode else "Auto Mode: OFF")

    def quit(self):
        self.tray.hide()
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    PixelCatApp().run()
