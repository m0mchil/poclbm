from sys import platform

WINDOWS = LINUX = MACOSX = None

WINDOWS = platform.startswith('win')
LINUX = platform.startswith('linux')
MACOSX = (platform == 'darwin')
