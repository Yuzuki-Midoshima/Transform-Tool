"""Transform Tool for Autodesk Maya 2026."""


def show():
    """Open the tool, importing Maya/PySide modules only when needed."""
    from .ui import show as show_window
    return show_window()


__all__ = ["show"]
