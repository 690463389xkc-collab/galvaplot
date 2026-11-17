"""Entry script for PyInstaller and for double-click runs from source."""
import sys

from galvaplot.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
