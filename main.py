"""
main.py
Launches the floating desktop character app.

Run with:  python main.py
"""
import sys
from PyQt5.QtWidgets import QApplication
from pet_window import PetWindow


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    pet = PetWindow()  # noqa: F841 (kept alive by reference here)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
