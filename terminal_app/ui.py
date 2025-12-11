import sys
import threading
import queue
import winsound
import signal
from typing import Callable, Dict, Optional

from PyQt6.QtWidgets import (QApplication, QWidget, QHBoxLayout, 
                             QPushButton, QFrame, QStackedWidget)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPoint
from PyQt6.QtGui import QColor, QPainter, QBrush, QCursor

class Communicator(QObject):
    status_signal = pyqtSignal(str)
    amplitude_signal = pyqtSignal(float)

class ModernButton(QPushButton):
    def __init__(self, text, color, hover_color, callback, size=36, font_size=16):
        super().__init__(text)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(callback)
        self.default_color = color
        self.hover_color = hover_color
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border-radius: {size//2}px;
                font-size: {font_size}px;
                border: none;
                font-family: Segoe UI Symbol;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {color};
            }}
        """)

    def update_color(self, color, hover_color):
        self.default_color = color
        self.hover_color = hover_color
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border-radius: {self.width()//2}px;
                font-size: 16px;
                border: none;
                font-family: Segoe UI Symbol;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {color};
            }}
        """)

class WaveformWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(100, 40)
        self.amplitudes = [0.0] * 30
        self.mode = "transcribe" # or prompt

    def update_data(self, amp):
        self.amplitudes.pop(0)
        self.amplitudes.append(amp)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        bar_width = self.width() / len(self.amplitudes)
        center_y = self.height() / 2
        
        # Color based on mode
        base_color = QColor("#3B82F6") if self.mode == "transcribe" else QColor("#A855F7")
        
        for i, amp in enumerate(self.amplitudes):
            # Calculate height
            h = max(4, amp * self.height())
            x = i * bar_width
            y = center_y - (h / 2)
            
            # Opacity based on amplitude
            color = QColor(base_color)
            color.setAlpha(int(150 + min(amp, 1.0) * 105))
            
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            
            # Draw rounded rect
            painter.drawRoundedRect(int(x), int(y), int(bar_width - 2), int(h), 2, 2)

class MainWindow(QWidget):
    def __init__(self, callbacks, communicator):
        super().__init__()
        self.callbacks = callbacks
        self.comm = communicator
        self.is_paused = False
        
        # Window setup
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Layout
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Main container (pill shape)
        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 20, 245);
                border-radius: 25px;
                border: 1px solid rgba(255, 255, 255, 20);
            }
        """)
        # Start with idle size
        self.container.setFixedSize(130, 50)
        self.setFixedSize(130, 50)
        
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(10, 5, 10, 5)
        self.container_layout.setSpacing(10)
        
        self.layout.addWidget(self.container)
        
        # Stack for modes
        self.stack = QStackedWidget()
        self.container_layout.addWidget(self.stack)
        
        # --- Idle Page ---
        self.idle_widget = QWidget()
        idle_layout = QHBoxLayout(self.idle_widget)
        idle_layout.setContentsMargins(0, 0, 0, 0)
        idle_layout.setSpacing(15)
        idle_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn_transcribe = ModernButton("🎤", "#3B82F6", "#2563EB", self.on_transcribe, size=36, font_size=18)
        self.btn_prompt = ModernButton("✨", "#A855F7", "#9333EA", self.on_prompt, size=36, font_size=18)
        
        idle_layout.addWidget(self.btn_transcribe)
        idle_layout.addWidget(self.btn_prompt)
        
        self.stack.addWidget(self.idle_widget)
        
        # --- Recording Page ---
        self.rec_widget = QWidget()
        rec_layout = QHBoxLayout(self.rec_widget)
        rec_layout.setContentsMargins(0, 0, 0, 0)
        rec_layout.setSpacing(8)
        
        self.waveform = WaveformWidget()
        
        self.btn_send = ModernButton("📤", "#38BDF8", "#0EA5E9", self.on_send, size=32, font_size=16)
        self.btn_pause = ModernButton("⏸", "#71717a", "#52525b", self.on_pause, size=32, font_size=16)
        self.btn_cancel = ModernButton("✖", "#ef4444", "#dc2626", self.on_cancel, size=32, font_size=16)
        
        rec_layout.addWidget(self.waveform)
        rec_layout.addWidget(self.btn_send)
        rec_layout.addWidget(self.btn_pause)
        rec_layout.addWidget(self.btn_cancel)
        
        self.stack.addWidget(self.rec_widget)
        
        # Connect signals
        self.comm.status_signal.connect(self.handle_status)
        self.comm.amplitude_signal.connect(self.waveform.update_data)
        
        # Dragging logic
        self.old_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def play_sound(self):
        try:
            threading.Thread(target=lambda: winsound.Beep(800, 50), daemon=True).start()
        except:
            pass

    def transition_to(self, mode):
        current_geometry = self.geometry()
        center_point = current_geometry.center()
        
        if mode == "idle":
            new_width = 130
            self.stack.setCurrentIndex(0)
        else:
            new_width = 270
            self.stack.setCurrentIndex(1)
            
        self.container.setFixedSize(new_width, 50)
        self.setFixedSize(new_width, 50)
        
        # Re-center horizontally, keep vertical position
        new_x = center_point.x() - (new_width // 2)
        self.move(new_x, current_geometry.y())

    def on_transcribe(self):
        self.play_sound()
        self.callbacks.get("start", lambda: None)()
        self.waveform.mode = "transcribe"
        self.transition_to("recording")
        self.update_send_button_color()

    def on_prompt(self):
        self.play_sound()
        self.callbacks.get("prompt", lambda: None)()
        self.waveform.mode = "prompt"
        self.transition_to("recording")
        self.update_send_button_color()

    def update_send_button_color(self):
        if self.waveform.mode == "prompt":
            self.btn_send.update_color("#9b59b6", "#8e44ad")
        else:
            self.btn_send.update_color("#87CEEB", "#5dade2")

    def on_send(self):
        self.play_sound()
        self.callbacks.get("stop", lambda: None)()
        self.transition_to("idle")

    def on_pause(self):
        self.play_sound()
        if self.is_paused:
             self.callbacks.get("resume", lambda: None)()
        else:
             self.callbacks.get("pause", lambda: None)()

    def on_cancel(self):
        self.play_sound()
        self.callbacks.get("cancel", lambda: None)()
        self.transition_to("idle")

    def handle_status(self, text):
        if "recording" in text:
            self.transition_to("recording")
            if "prompt" in text:
                self.waveform.mode = "prompt"
            else:
                self.waveform.mode = "transcribe"
            self.update_send_button_color()
            
            self.is_paused = False
            self.btn_pause.setText("⏸")
            self.btn_pause.update_color("#7f8c8d", "#95a5a6")
            
        elif "paused" in text:
            self.is_paused = True
            self.btn_pause.setText("▶")
            self.btn_pause.update_color("#3498db", "#2980b9")
            
        elif "idle" in text:
            self.transition_to("idle")
            self.is_paused = False

class WaveformWindow:
    def __init__(self, amplitude_queue, width=420, height=175, callbacks=None):
        self.queue = amplitude_queue
        self.callbacks = callbacks or {}
        self.comm = Communicator()
        self.app = None
        self.window = None

    def update_status(self, text: str) -> None:
        self.comm.status_signal.emit(text)

    def run(self):
        # Create QApplication if it doesn't exist
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        self.app = app
        
        self.window = MainWindow(self.callbacks, self.comm)
        
        # Center on screen initially
        screen_geometry = self.app.primaryScreen().geometry()
        x = (screen_geometry.width() - self.window.width()) // 2
        y = (screen_geometry.height() - self.window.height()) // 2
        self.window.move(x, y)
        
        self.window.show()
        
        # Timer for amplitude processing
        timer = QTimer()
        timer.timeout.connect(self._process_queue)
        timer.start(30) # 30ms update rate
        
        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, lambda *args: self.app.quit())
        
        # Timer to allow Python to process signals
        ctrl_c_timer = QTimer()
        ctrl_c_timer.timeout.connect(lambda: None)
        ctrl_c_timer.start(100)
        
        self.app.exec()

    def _process_queue(self):
        try:
            while not self.queue.empty():
                amp = self.queue.get_nowait()
                self.comm.amplitude_signal.emit(float(amp))
        except:
            pass


