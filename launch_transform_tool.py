"""Maya Script Editor and shelf entry point with development-safe reloads."""

from importlib import reload

from transform_tool import naming

reload(naming)

from transform_tool import operations

reload(operations)

from transform_tool import ui

reload(ui)
ui.show()
