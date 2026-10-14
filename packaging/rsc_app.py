"""Entry point PyInstaller wraps into RSC.app."""
import sys

from rsc import desktop

if __name__ == "__main__":
    sys.exit(desktop.main())
