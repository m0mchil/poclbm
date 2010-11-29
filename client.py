#!/usr/bin/python

import sys
import numpy as np
import pyopencl as cl

from struct import *
from time import sleep, time
from datetime import datetime
from jsonrpc import ServiceProxy
from optparse import OptionParser
from jsonrpc.proxy import JSONRPCException

from BitcoinMiner import *

def sysWrite(format, args=()):
        sys.stdout.write('\r                                        \r' + format % args)
        sys.stdout.flush()

def sysWriteLn(format, args=()):
        sysWrite(format + '\n', args)

parser = OptionParser()
parser.add_option('-u', '--user',     dest='user',     default='bitcoin',   help='user name')
parser.add_option('--pass',           dest='password', default='password',  help='password')
parser.add_option('-o', '--host',     dest='host',     default='127.0.0.1', help='RPC host')
parser.add_option('-p', '--port',     dest='port',     default='8332',      help='RPC port')
parser.add_option('-r', '--rate',     dest='rate',     default=1,           help='hash rate display interval in seconds, default=1', type='float')
parser.add_option('-f', '--frames',   dest='frames',   default=60,          help='will try to bring single kernel execution to 1/frames seconds, default=60, increase this for less desktop lag', type='float')
parser.add_option('-d', '--device',   dest='device',   default=-1,          help='use device by id, by default asks for device', type='int')
parser.add_option('-a', '--askrate',  dest='askrate',  default=5,           help='how many seconds between getwork requests, default 5, max 30', type='int')
parser.add_option('-w', '--worksize', dest='worksize', default=-1,          help='work group size, default is maximum returned by opencl', type='int')
parser.add_option('-v', '--vectors',  dest='vectors',  action='store_true', help='use vectors')
(options, args) = parser.parse_args()
options.frames = max(options.frames, 1.1)
options.askrate = max(options.askrate, 1)
options.askrate = min(options.askrate, 30)

platform = cl.get_platforms()[0]

if (options.device != -1):
        devices = platform.get_devices()
        context = cl.Context([devices[options.device]], None, None)
else:
        print 'No device specified, you may use -d to specify ONLY ONE of the following\n'
        context = cl.create_some_context()

myMiner = BitcoinMiner(platform, context, options.host, options.user, options.password, options.port, options.frames, options.rate, options.askrate, options.worksize, options.vectors)
myMiner.mine()

