from __future__ import annotations

import os

import pytest
from PySide6.QtCore import QCoreApplication, QSettings

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")
os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.getcwd(), "runs", ".gui_cache"))


@pytest.fixture(autouse=True)
def isolate_qsettings():
    app = QCoreApplication.instance()
    if app is not None:
        app.setOrganizationName("Federica Research Lab")
        app.setApplicationName("PGG, Porous Geometry Generation")
    q = QSettings()
    q.clear()
    yield
    q.clear()
