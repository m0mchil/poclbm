from distutils.core import setup
try:
    import py2exe
except ImportError:
    py2exe = None

args = {}
args['console'] = ['poclbm.py']
args['data_files'] = ['phatk.cl', 'msvcp90.dll']

if py2exe != None:
    args.update({
        # py2exe options
        'options': {'py2exe':
                      {'optimize': 2,
                       'bundle_files': 2,
                       'compressed': True,
                       'dll_excludes': ['OpenCL.dll'],
                       'excludes': ["Tkconstants", "Tkinter", "tcl"],
                      },
                  },
        'zipfile': None,
    })

setup(**args)
