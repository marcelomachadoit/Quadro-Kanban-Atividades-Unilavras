"""Gera assets/icon.ico (ícone do aplicativo) usando o próprio Qt."""
import sys
from pathlib import Path
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

app = QGuiApplication(sys.argv)
img = QImage(256, 256, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
p.setPen(Qt.NoPen)
p.setBrush(QColor("#0F1B2D"))
p.drawRoundedRect(QRectF(8, 8, 240, 240), 52, 52)
for i, (h, c) in enumerate(((150, "#60A5FA"), (110, "#2563EB"), (70, "#10B981"))):
    p.setBrush(QColor(c))
    p.drawRoundedRect(QRectF(44 + i * 60, 52, 46, h), 12, 12)
p.end()
out = Path(__file__).with_name("icon.ico")
img.save(str(out))
img.save(str(out.with_suffix(".png")))
print("ok", out)
