#!/usr/bin/python

import pyopencl as cl
from optparse import OptionParser
from BitcoinMiner import *

parser = OptionParser()
parser.add_option('-u', '--user',     dest='user',     default='bitcoin',   help='user name')
parser.add_option('--pass',	          dest='password', default='password',  help='password')
parser.add_option('-o', '--host',	  dest='host',     default='127.0.0.1', help='RPC host')
parser.add_option('-p', '--port',	  dest='port',     default='8332',      help='RPC port')
parser.add_option('-r', '--rate',	  dest='rate',     default=1,           help='hash rate display interval in seconds, default=1', type='float')
parser.add_option('-f', '--frames',   dest='frames',   default=60,          help='will try to bring single kernel execution to 1/frames seconds, default=60, increase this for less desktop lag', type='float')
parser.add_option('-d', '--device',   dest='device',   default=-1,          help='use device by id, by default asks for device', type='int')
parser.add_option('-a', '--askrate',  dest='askrate',  default=5,           help='how many seconds between getwork requests, default 5, max 30', type='int')
parser.add_option('-w', '--worksize', dest='worksize', default=-1,          help='work group size, default is maximum returned by opencl', type='int')
parser.add_option('-v', '--vectors',  dest='vectors',  action='store_true', help='use vectors')
(options, args) = parser.parse_args()

platform = cl.get_platforms()[0]
devices = platform.get_devices()

if (options.device == -1 or options.device >= len(devices)):
	print 'No device specified or device not found, use -d to specify one of the following\n'
	for i in xrange(len(devices)):
		print '[%d]\t%s' % (i, devices[i].name)
	sys.exit()

context = cl.Context([devices[options.device]], None, None)
myMiner = BitcoinMiner(platform, context, options.host, options.user, options.password, options.port, options.frames, options.rate, options.askrate, options.worksize, options.vectors)
myMiner.mine()