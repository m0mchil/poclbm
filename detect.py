WINDOWS = LINUX = None

try:
	from platform import system
	WINDOWS = system() == 'Windows'
	LINUX = system() == 'Linux'
except ImportError:
	pass