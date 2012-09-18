#!/usr/bin/python

from BitcoinMiner import *
from optparse import OptionGroup, OptionParser
from time import sleep
import Servers
import pyopencl as cl
import socket

try:
	from adl3 import ADL_Main_Control_Create, ADL_Main_Memory_Alloc, ADL_Main_Control_Destroy, ADL_OK
except ImportError:
	print '\nWARNING: no adl3 module found (github.com/mjmvisser/adl3), temperature control is disabled\n'

# Socket wrapper to enable socket.TCP_NODELAY and KEEPALIVE
realsocket = socket.socket
def socketwrap(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
	sockobj = realsocket(family, type, proto)
	sockobj.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
	sockobj.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
	return sockobj
socket.socket = socketwrap

VERSION = '20120205'

usage = "usage: %prog [OPTION]... SERVER[#tag]...\nSERVER is one or more [http[s]|stratum://]user:pass@host:port          (required)\n[#tag] is a per SERVER user friendly name displayed in stats (optional)"
parser = OptionParser(version=VERSION, usage=usage)
parser.add_option('--verbose',        dest='verbose',    action='store_true', help='verbose output, suitable for redirection to log file')
parser.add_option('-q', '--quiet',    dest='quiet',      action='store_true', help='suppress all output except hash rate display')
parser.add_option('--proxy',          dest='proxy',      default='',          help='specify as [[socks4|socks5|http://]user:pass@]host:port (default proto is socks5)')

group = OptionGroup(parser, "Miner Options")
group.add_option('-r', '--rate',          dest='rate',       default=1,       help='hash rate display interval in seconds, default=1 (60 with --verbose)', type='float')
group.add_option('-e', '--estimate',      dest='estimate',   default=900,     help='estimated rate time window in seconds, default 900 (15 minutes)', type='int')
group.add_option('-a', '--askrate',       dest='askrate',    default=5,       help='how many seconds between getwork requests, default 5, max 10', type='int')
group.add_option('-t', '--tolerance',     dest='tolerance',  default=2,       help='use fallback pool only after N consecutive connection errors, default 2', type='int')
group.add_option('-b', '--failback',      dest='failback',   default=60,      help='attempt to fail back to the primary pool after N seconds, default 60', type='int')
group.add_option('--cutoff_temp',         dest='cutoff_temp',default=95,      help='(requires github.com/mjmvisser/adl3) temperature at which to skip kernel execution, in C, default=95', type='float')
group.add_option('--cutoff_interval',     dest='cutoff_interval',default=0.01, help='(requires adl3) how long to not execute calculations if CUTOFF_TEMP is reached, in seconds, default=0.01', type='float')
group.add_option('--no-server-failbacks', dest='nsf',        action='store_true', help='disable using failback hosts provided by server')
parser.add_option_group(group)

group = OptionGroup(parser, "Kernel Options")
group.add_option('-p', '--platform', dest='platform',   default=-1,          help='use platform by id', type='int')
group.add_option('-d', '--device',   dest='device',     default=-1,          help='use device by id, by default asks for device', type='int')
group.add_option('-w', '--worksize', dest='worksize',   default=-1,          help='work group size, default is maximum returned by opencl', type='int')
group.add_option('-f', '--frames',   dest='frames',     default=30,          help='will try to bring single kernel execution to 1/frames seconds, default=30, increase this for less desktop lag', type='int')
group.add_option('-s', '--sleep',    dest='frameSleep', default=0,           help='sleep per frame in seconds, default 0', type='float')
group.add_option('-v', '--vectors',  dest='vectors',    action='store_true', help='use vectors')
parser.add_option_group(group)

(options, options.servers) = parser.parse_args()


platforms = cl.get_platforms()

if options.platform >= len(platforms) or (options.platform == -1 and len(platforms) > 1):
	print 'Wrong platform or more than one OpenCL platforms found, use --platform to select one of the following\n'
	for i in xrange(len(platforms)):
		print '[%d]\t%s' % (i, platforms[i].name)
	sys.exit()

if options.platform == -1:
	options.platform = 0

devices = platforms[options.platform].get_devices()
if (options.device == -1 or options.device >= len(devices)):
	print 'No device specified or device not found, use -d to specify one of the following\n'
	for i in xrange(len(devices)):
		print '[%d]\t%s' % (i, devices[i].name)
	sys.exit()

miner = None
try:
	#init adl
	try:
		ADL_OK
		if ADL_Main_Control_Create(ADL_Main_Memory_Alloc, 1) != ADL_OK:
			print "Couldn't initialize ADL interface."
			sys.exit()
	except NameError:
		pass
	#end init adl

	miner = BitcoinMiner(devices[options.device], options, VERSION, Servers.Servers)
	miner.start()
except KeyboardInterrupt:
	print '\nbye'
finally:
	if miner: miner.stop()

	#adl shutdown
	try:
		ADL_OK
		ADL_Main_Control_Destroy()
	except NameError:
		pass
	#end adl shutdown
sleep(1.1)
