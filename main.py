import sys

from gui.main_window import MainWindow, qt_available


def main(argv=None):
    args = list(sys.argv if argv is None else argv)
    if not qt_available():
        sys.stderr.write("PySide6 is not installed; GUI bootstrap is unavailable.\n")
        return 1

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(args)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
