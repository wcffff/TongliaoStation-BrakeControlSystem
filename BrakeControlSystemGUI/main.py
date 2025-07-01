import sys

from PyQt5.QtWidgets import QApplication

from modules.gui import BrakeControlSystemGUI

if __name__ == "__main__":
    machine_id = "A"
    app = QApplication(sys.argv)
    window = BrakeControlSystemGUI(machine_id)
    window.show()
    sys.exit(app.exec_())
