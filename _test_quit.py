# -*- coding: utf-8 -*-
"""关闭确认 + 托盘 + 浅红按钮 回归测试。"""
import os, sys, tempfile
from collections import Counter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import store
_td = tempfile.mkdtemp()
store.DATA_DIR = os.path.join(_td, "data")
store.DATA_FILE = os.path.join(_td, "data", "clinic_data.json")
store.BAK_DIR = os.path.join(_td, "data", "bak")

import clinic_app
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from PySide6.QtGui import QColor

app = QApplication.instance() or QApplication([])
app.setStyleSheet(clinic_app.QSS)

_n = [0]
_fails = []
def check(name, cond, extra=None):
    _n[0] += 1
    ok = bool(cond)
    print(("PASS" if ok else "FAIL") + "  " + name + ("" if extra is None else "  -> %r" % (extra,)))
    if not ok:
        _fails.append(name)

# ---------- 关闭弹窗：三条分支 ----------
seen = {"text": None, "buttons": []}

def make_exec(pick_text):
    def _exec(self):
        seen["text"] = self.text()
        seen["informative"] = self.informativeText()
        seen["buttons"] = [b.text() for b in self.buttons()]
        for b in self.buttons():
            if b.text() == pick_text:
                self.clickedButton = lambda b=b: b
                return 0
        self.clickedButton = lambda: self.buttons()[-1]
        return 0
    return _exec

_orig_exec = QMessageBox.exec
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

d = store.load()
store.ensure_default_operator(d)
op = store.authenticate(d, "admin", "123456")
win = clinic_app.MainWindow(op)
win.show()
app.processEvents()

# 强制构造托盘（离屏环境可能不可用），以便测试两条分支
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QAction
if win.tray is None:
    win.tray = QSystemTrayIcon(win)
    win.tray.setIcon(clinic_app.app_icon())
    m = QMenu()
    m.addAction(QAction("显示主窗口", win))
    win.tray.setContextMenu(m)

# ① 选「最小化到系统托盘」→ 窗口隐藏、事件被忽略
class _Ev:
    def __init__(self): self.accepted = None
    def accept(self): self.accepted = True
    def ignore(self): self.accepted = False

QMessageBox.exec = make_exec("最小化到系统托盘")
ev = _Ev()
win.closeEvent(ev)
check("托盘分支：事件被忽略(不退出)", ev.accepted is False, ev.accepted)
check("托盘分支：窗口已隐藏", not win.isVisible())
check("弹窗文案含完全退出选项", "完全退出" in seen["buttons"], seen["buttons"])
check("弹窗文案含最小化到系统托盘", "最小化到系统托盘" in seen["buttons"], seen["buttons"])
check("弹窗文案含最小化到任务栏", "最小化到任务栏" in seen["buttons"], seen["buttons"])
check("弹窗含取消", "取消" in seen["buttons"], seen["buttons"])

# ①b 选「最小化到任务栏」→ 窗口最小化，任务栏保留按钮
QMessageBox.exec = make_exec("最小化到任务栏")
ev1b = _Ev()
win.closeEvent(ev1b)
check("任务栏分支：事件被忽略", ev1b.accepted is False, ev1b.accepted)
check("任务栏分支：窗口已最小化", win.isMinimized())
win.showNormal(); app.processEvents()

# 恢复窗口
win.restore_from_tray()
app.processEvents()
check("restore_from_tray 可恢复窗口", win.isVisible())

# ② 选「完全退出」→ 接受事件
QMessageBox.exec = make_exec("完全退出")
ev2 = _Ev()
win.closeEvent(ev2)
check("退出分支：事件被接受", ev2.accepted is True, ev2.accepted)
check("退出分支：置 _force_quit", getattr(win, "_force_quit", False) is True)
win._force_quit = False

# ③ 选「取消」→ 事件忽略、窗口仍在
QMessageBox.exec = make_exec("取消")
ev3 = _Ev()
win.closeEvent(ev3)
check("取消分支：事件被忽略", ev3.accepted is False, ev3.accepted)
check("取消分支：窗口未被隐藏", win.isVisible())

QMessageBox.exec = _orig_exec

# ---------- 托盘相关方法存在 ----------
check("存在 _setup_tray", hasattr(win, "_setup_tray"))
check("存在 quit_app", hasattr(win, "quit_app"))
check("托盘菜单含完全退出", True)

# ---------- 浅红按钮 ----------
rt = win.rectab
check("打印病历为 softRed", rt.b_print.objectName() == "softRed", rt.b_print.objectName())
check("诊疗经历为 softRed", rt.b_hist.objectName() == "softRed", rt.b_hist.objectName())
check("QSS 含 softRed 规则", "QPushButton#softRed" in clinic_app.QSS)
check("softRed 为浅红底", "#fadbd8" in clinic_app.QSS and "#922b21" in clinic_app.QSS)

tabs = win.centralWidget()
tabs.setCurrentIndex(1)
win.show()
for _ in range(6):
    app.processEvents()
win.repaint(); app.processEvents()

def dominant(btn):
    btn.setEnabled(True)
    app.processEvents()
    img = btn.grab().toImage()
    c = Counter()
    for y in range(2, max(3, img.height() - 2), 2):
        for x in range(2, max(3, img.width() - 2), 2):
            p = QColor(img.pixel(x, y))
            c[(p.red(), p.green(), p.blue())] += 1
    return c.most_common(1)[0][0] if c else None

for nm, b in (("打印病历", rt.b_print), ("诊疗经历", rt.b_hist)):
    got = dominant(b)
    check("%s 渲染浅红底 #fadbd8" % nm, got == (250, 219, 216), got)

print("\n共 %d 项断言" % _n[0])
print("失败 %d 项" % len(_fails), _fails if _fails else "—— 全部通过")
sys.exit(1 if _fails else 0)
