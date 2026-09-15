"""
pet_window.py
The floating, always-on-top, frameless character window plus its
right-click feature menu (hide, resize, opacity, speed, stop animation,
float across screen, add media, choose character...).
"""
import os
import random
import math
from PyQt5.QtWidgets import (
    QWidget, QLabel, QMenu, QAction, QActionGroup, QFileDialog,
    QSystemTrayIcon, QApplication, QInputDialog
)
from PyQt5.QtGui import QPixmap, QMovie, QIcon, QCursor
from PyQt5.QtCore import Qt, QTimer, QPoint, QSize, QRect

from video_utils import media_kind, VideoSpriteReader, bgr_frame_to_qimage
from video_downloader import VideoDownloaderThread
import config_manager


class PetWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.config = config_manager.load_config()

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool  # keeps it off the taskbar / alt-tab list
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)

        self.label = QLabel(self)
        self.label.setScaledContents(True)

        self._drag_offset = None
        self._movie = None            # for GIFs
        self._video_reader = None     # for chroma-keyed video
        self._video_timer = QTimer(self)
        self._video_timer.timeout.connect(self._advance_video_frame)
        self._paused = False
        self._user_hidden = False       # hidden because the USER chose Hide
        self._auto_hidden = False       # hidden because a fullscreen app is active
        self._download_thread = None

        # Floating / roaming screen physics state
        self._roam_enabled = self.config.get("roam_enabled", True)
        self._roam_speed = self.config.get("roam_speed", 1.5)
        self._vx = 1.2
        self._vy = 0.8
        self._pos_float_x = float(self.config["pos_x"])
        self._pos_float_y = float(self.config["pos_y"])
        self._roam_change_counter = 0

        self._roam_timer = QTimer(self)
        self._roam_timer.timeout.connect(self._update_roam_position)
        if self._roam_enabled:
            self._roam_timer.start(30)

        self.move(self.config["pos_x"], self.config["pos_y"])
        self.setWindowOpacity(self.config["opacity"])

        self._build_tray_icon()
        self._load_media(self.config.get("current_media"))
        self.show()

        # Watches for fullscreen apps so the pet can hide/reappear automatically
        self._fullscreen_timer = QTimer(self)
        self._fullscreen_timer.timeout.connect(self._check_fullscreen)
        self._fullscreen_timer.start(1000)

    # ------------------------------------------------------------------
    # Media loading / playback
    # ------------------------------------------------------------------
    def _load_media(self, path):
        if not path or not os.path.exists(path):
            self._show_placeholder()
            return

        self._stop_all_playback()
        kind = media_kind(path)

        if kind == "gif":
            self._movie = QMovie(path)
            self._movie.setScaledSize(self._target_size())
            self.label.setMovie(self._movie)
            self._movie.start()
            if self._paused:
                self._movie.setPaused(True)

        elif kind == "image":
            pix = QPixmap(path)
            self.label.setPixmap(pix.scaled(
                self._target_size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        elif kind == "video":
            try:
                self._video_reader = VideoSpriteReader(path)
            except IOError as e:
                print(e)
                self._show_placeholder()
                return
            base_interval_ms = int(1000 / max(self._video_reader.fps, 1))
            interval = max(1, int(base_interval_ms / self.config["speed"]))
            if not self._paused:
                self._video_timer.start(interval)
            self._advance_video_frame()  # draw first frame immediately

        else:
            self._show_placeholder()
            return

        self.config["current_media"] = path
        if path not in self.config["media_library"]:
            self.config["media_library"].append(path)
        self._apply_geometry()
        config_manager.save_config(self.config)

    def _show_placeholder(self):
        self.label.setText("Right-click\nto add a\ncharacter")
        self.label.setStyleSheet("color: white; background: rgba(0,0,0,120); "
                                  "border-radius: 12px; padding: 10px;")
        self.label.setAlignment(Qt.AlignCenter)
        size = self._target_size()
        self.resize(size)
        self.label.resize(size)

    def _stop_all_playback(self):
        if self._movie:
            self._movie.stop()
            self._movie = None
        if self._video_timer.isActive():
            self._video_timer.stop()
        if self._video_reader:
            self._video_reader.release()
            self._video_reader = None
        self.label.setStyleSheet("")
        self.label.setText("")

    def _advance_video_frame(self):
        if not self._video_reader:
            return
        frame = self._video_reader.read_next_frame()
        if frame is None:
            return
        qimg = bgr_frame_to_qimage(
            frame, self.config["chroma_lower"], self.config["chroma_upper"])
        pix = QPixmap.fromImage(qimg).scaled(
            self._target_size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label.setPixmap(pix)
        self.resize(pix.size())
        self.label.resize(pix.size())

    def _target_size(self) -> QSize:
        h = self.config["size"]
        return QSize(int(h * 0.8), h)  # aspect box default; media scales to fit inside

    def _apply_geometry(self):
        size = self._target_size()
        self.resize(size)
        self.label.resize(size)

    # ------------------------------------------------------------------
    # Floating / Roaming Physics
    # ------------------------------------------------------------------
    def _update_roam_position(self):
        if not self._roam_enabled or self._drag_offset is not None or self.isHidden():
            return

        # Occasionally add a slight random angle variation for natural wandering motion
        self._roam_change_counter += 1
        if self._roam_change_counter > 100:  # ~every 3 seconds
            self._roam_change_counter = 0
            angle_delta = (random.random() - 0.5) * 0.5
            speed = math.hypot(self._vx, self._vy)
            if speed < 0.2:
                speed = 1.2
            curr_angle = math.atan2(self._vy, self._vx)
            new_angle = curr_angle + angle_delta
            self._vx = math.cos(new_angle) * speed
            self._vy = math.sin(new_angle) * speed

        # Move float coordinates
        step = self._roam_speed
        self._pos_float_x += self._vx * step
        self._pos_float_y += self._vy * step

        # Get active screen bounds (full screen geometry)
        curr_rect = QRect(int(self._pos_float_x), int(self._pos_float_y), self.width(), self.height())
        screen = QApplication.screenAt(curr_rect.center()) or QApplication.primaryScreen()
        if screen:
            full_bounds = screen.geometry()
        else:
            full_bounds = QRect(0, 0, 1920, 1080)

        # Allow 50% off-screen float on all sides (left, right, top, and over the taskbar at bottom)
        offset_x = int(self.width() * 0.5)
        offset_y = int(self.height() * 0.5)

        min_x = full_bounds.left() - offset_x
        max_x = full_bounds.right() - offset_x
        min_y = full_bounds.top() - offset_y
        max_y = full_bounds.bottom() - offset_y

        # Bounce off screen edges smoothly
        if self._pos_float_x <= min_x:
            self._pos_float_x = min_x
            self._vx = abs(self._vx)
        elif self._pos_float_x >= max_x:
            self._pos_float_x = max_x
            self._vx = -abs(self._vx)

        if self._pos_float_y <= min_y:
            self._pos_float_y = min_y
            self._vy = abs(self._vy)
        elif self._pos_float_y >= max_y:
            self._pos_float_y = max_y
            self._vy = -abs(self._vy)

        self.move(int(self._pos_float_x), int(self._pos_float_y))

    # ------------------------------------------------------------------
    # Right-click feature menu
    # ------------------------------------------------------------------
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #222; color: white; border: 1px solid #555; }"
            "QMenu::item:selected { background-color: #444; }"
        )

        hide_action = menu.addAction("Hide")
        hide_action.triggered.connect(self.hide_character)

        pause_text = "Resume Animation" if self._paused else "Stop Animation"
        pause_action = menu.addAction(pause_text)
        pause_action.triggered.connect(self.toggle_pause)

        roam_action = menu.addAction("Float Across Screen")
        roam_action.setCheckable(True)
        roam_action.setChecked(self._roam_enabled)
        roam_action.triggered.connect(self.toggle_roam)

        menu.addSeparator()
        menu.addMenu(self._build_size_menu())
        menu.addMenu(self._build_opacity_menu())
        menu.addMenu(self._build_speed_menu())
        menu.addSeparator()

        add_media_action = menu.addAction("Add Video / Image...")
        add_media_action.triggered.connect(self.add_media)

        add_url_action = menu.addAction("Add Video from Link...")
        add_url_action.triggered.connect(self.add_media_from_url)

        if self.config["media_library"]:
            menu.addMenu(self._build_library_menu())

        menu.addSeparator()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(QApplication.quit)

        menu.exec_(event.globalPos())

    def _build_size_menu(self):
        m = QMenu("Change Size", self)
        group = QActionGroup(self)
        sizes = [
            ("50% (100px)", 100),
            ("75% (150px)", 150),
            ("100% (200px)", 200),
            ("150% (300px)", 300),
            ("200% (400px)", 400),
            ("300% (600px)", 600),
            ("400% (800px)", 800),
            ("500% (1000px)", 1000),
        ]
        for label, px in sizes:
            act = QAction(label, self, checkable=True)
            act.setChecked(self.config["size"] == px)
            act.triggered.connect(lambda checked, v=px: self._set_size(v))
            group.addAction(act)
            m.addAction(act)
        m.addSeparator()
        custom = m.addAction("Custom...")
        custom.triggered.connect(self._set_custom_size)
        return m

    def _build_opacity_menu(self):
        m = QMenu("Opacity", self)
        group = QActionGroup(self)
        for label, val in [("25%", 0.25), ("50%", 0.5), ("75%", 0.75), ("100%", 1.0)]:
            act = QAction(label, self, checkable=True)
            act.setChecked(abs(self.config["opacity"] - val) < 0.01)
            act.triggered.connect(lambda checked, v=val: self._set_opacity(v))
            group.addAction(act)
            m.addAction(act)
        return m

    def _build_speed_menu(self):
        m = QMenu("Speed", self)
        group = QActionGroup(self)
        speeds = [
            ("0.10x (Slowest)", 0.10),
            ("0.25x", 0.25),
            ("0.5x", 0.50),
            ("0.75x", 0.75),
            ("1x (Normal)", 1.0),
            ("1.5x", 1.5),
            ("2x", 2.0),
            ("3x", 3.0),
            ("4x", 4.0),
            ("5x (Ultra Fast)", 5.0),
        ]
        for label, val in speeds:
            act = QAction(label, self, checkable=True)
            act.setChecked(abs(self.config["speed"] - val) < 0.01)
            act.triggered.connect(lambda checked, v=val: self._set_speed(v))
            group.addAction(act)
            m.addAction(act)
        m.addSeparator()
        custom = m.addAction("Custom Speed...")
        custom.triggered.connect(self._set_custom_speed)
        return m

    def _build_library_menu(self):
        m = QMenu("Choose Character", self)
        for path in self.config["media_library"]:
            name = os.path.basename(path)
            act = QAction(name, self)
            act.triggered.connect(lambda checked, p=path: self._load_media(p))
            m.addAction(act)
        return m

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def hide_character(self):
        self._user_hidden = True
        self.hide()
        if self._tray:
            self._tray.showMessage("Desktop Pet", "Hidden. Use the tray icon to bring it back.",
                                    QSystemTrayIcon.Information, 2000)

    def show_character(self):
        self._user_hidden = False
        if not self._auto_hidden:
            self.show()

    def toggle_pause(self):
        self._paused = not self._paused
        if self._movie:
            self._movie.setPaused(self._paused)
        if self._paused:
            self._video_timer.stop()
        elif self._video_reader:
            self._video_timer.start()

    def toggle_roam(self):
        self._roam_enabled = not self._roam_enabled
        self.config["roam_enabled"] = self._roam_enabled
        if self._roam_enabled:
            self._pos_float_x = float(self.x())
            self._pos_float_y = float(self.y())
            self._roam_timer.start(30)
        else:
            self._roam_timer.stop()
        config_manager.save_config(self.config)

    def _set_size(self, px):
        self.config["size"] = px
        self._reload_current()
        config_manager.save_config(self.config)

    def _set_custom_size(self):
        val, ok = QInputDialog.getInt(
            self,
            "Custom Size",
            "Height in pixels (200px = 100%, 1000px = 500%):",
            self.config["size"],
            40,
            2000,
            10
        )
        if ok:
            self._set_size(val)

    def _set_opacity(self, val):
        self.config["opacity"] = val
        self.setWindowOpacity(val)
        config_manager.save_config(self.config)

    def _set_speed(self, val):
        val = max(0.10, min(5.0, float(val)))
        self.config["speed"] = val
        self._roam_speed = 1.5 * val
        self.config["roam_speed"] = self._roam_speed

        if self._movie:
            self._movie.setSpeed(int(val * 100))
        if self._video_reader:
            interval = max(1, int((1000 / max(self._video_reader.fps, 1)) / val))
            self._video_timer.setInterval(interval)

        config_manager.save_config(self.config)

    def _set_custom_speed(self):
        val, ok = QInputDialog.getDouble(
            self,
            "Custom Speed",
            "Speed multiplier (0.10x to 5.0x):",
            self.config["speed"],
            0.10,
            5.0,
            2
        )
        if ok:
            self._set_speed(val)

    def _reload_current(self):
        self._load_media(self.config.get("current_media"))

    def add_media(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a character image, GIF, or green-screen video", "",
            "Media Files (*.png *.webp *.gif *.mp4 *.mov *.webm *.avi *.mkv)"
        )
        if path:
            self._load_media(path)

    def add_media_from_url(self):
        url, ok = QInputDialog.getText(
            self,
            "Add Video from Link",
            "Paste YouTube or direct video link:"
        )
        if ok and url.strip():
            url = url.strip()
            assets_dir = os.path.join(config_manager.get_app_dir(), "assets")

            if self._tray:
                self._tray.showMessage(
                    "Desktop Pet",
                    "Downloading video link...",
                    QSystemTrayIcon.Information,
                    3000
                )
            self.label.setText("Downloading\nvideo link...")
            self.label.setStyleSheet("color: white; background: rgba(0,0,0,160); "
                                      "border-radius: 12px; padding: 10px;")
            self.label.setAlignment(Qt.AlignCenter)

            self._download_thread = VideoDownloaderThread(url, assets_dir)
            self._download_thread.download_finished.connect(self._on_download_success)
            self._download_thread.download_failed.connect(self._on_download_error)
            self._download_thread.start()

    def _on_download_success(self, filepath):
        if self._tray:
            self._tray.showMessage(
                "Desktop Pet",
                "Video downloaded successfully!",
                QSystemTrayIcon.Information,
                2000
            )
        self._load_media(filepath)

    def _on_download_error(self, err_msg):
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.warning(self, "Download Error", err_msg)
        self._reload_current()

    # ------------------------------------------------------------------
    # Dragging the character around with the left mouse button
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_offset and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPos() - self._drag_offset
            self.move(new_pos)
            self._pos_float_x = float(new_pos.x())
            self._pos_float_y = float(new_pos.y())

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        self._pos_float_x = float(self.x())
        self._pos_float_y = float(self.y())
        self.config["pos_x"] = self.x()
        self.config["pos_y"] = self.y()
        config_manager.save_config(self.config)

    # ------------------------------------------------------------------
    # System tray (lets the user bring the pet back after hiding it)
    # ------------------------------------------------------------------
    def _build_tray_icon(self):
        self._tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(QApplication.style().standardIcon(
            QApplication.style().SP_ComputerIcon))
        self._tray.setToolTip("Desktop Pet")

        menu = QMenu()
        show_act = menu.addAction("Show Character")
        show_act.triggered.connect(self.show_character)
        hide_act = menu.addAction("Hide Character")
        hide_act.triggered.connect(self.hide_character)
        menu.addSeparator()
        quit_act = menu.addAction("Exit")
        quit_act.triggered.connect(QApplication.quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda reason: self.show_character() if reason == QSystemTrayIcon.Trigger else None)
        self._tray.show()

    # ------------------------------------------------------------------
    # Auto-hide when something else is fullscreen on screen
    # ------------------------------------------------------------------
    def _check_fullscreen(self):
        if not self.config.get("auto_hide_on_fullscreen", True):
            return
        try:
            from fullscreen_watcher import is_foreground_window_fullscreen
            own_hwnds = {int(self.winId())}
            fullscreen_now = is_foreground_window_fullscreen(own_hwnds)
        except Exception:
            fullscreen_now = False

        if fullscreen_now and not self._auto_hidden:
            self._auto_hidden = True
            self.hide()
        elif not fullscreen_now and self._auto_hidden:
            self._auto_hidden = False
            if not self._user_hidden:
                self.show()

    def closeEvent(self, event):
        self._stop_all_playback()
        config_manager.save_config(self.config)
        event.accept()
