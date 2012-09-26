#!/usr/bin/python

from BitcoinMiner import *
from optparse import OptionGroup, OptionParser
from time import sleep
import Servers
import log
import pyopencl as cl
import socket

def tokenize(option, name, cast=int):
	if option:
		try:
			return [cast(x) for x in option.split(',')]
		except ValueError:
			log.say_exception('Invalid %s(s) specified: %s\n\n' % (name, option))
			sys.exit()
	return []

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
	sockobj.settimeout(5)
	return sockobj
socket.socket = socketwrap

VERSION = '20120920'

usage = "usage: %prog [OPTION]... SERVER[#tag]...\nSERVER is one or more [http[s]|stratum://]user:pass@host:port          (required)\n[#tag] is a per SERVER user friendly name displayed in stats (optional)"
parser = OptionParser(version=VERSION, usage=usage)
parser.add_option('--verbose',        dest='verbose',    action='store_true', help='verbose output, suitable for redirection to log file')
parser.add_option('-q', '--quiet',    dest='quiet',      action='store_true', help='suppress all output except hash rate display')
parser.add_option('--proxy',          dest='proxy',      default='',          help='specify as [[socks4|socks5|http://]user:pass@]host:port (default proto is socks5)')

group = OptionGroup(parser, "Miner Options")
group.add_option('-r', '--rate',          dest='rate',       default=1,       help='hash rate display interval in seconds, default=1 (60 with --verbose)', type='float')
group.add_option('-e', '--estimate',      dest='estimate',   default=900,     help='estimated rate time window in seconds, default 900 (15 minutes)', type='int')
group.add_option('-t', '--tolerance',     dest='tolerance',  default=2,       help='use fallback pool only after N consecutive connection errors, default 2', type='int')
group.add_option('-b', '--failback',      dest='failback',   default=60,      help='attempt to fail back to the primary pool after N seconds, default 60', type='int')
group.add_option('--cutoff_temp',         dest='cutoff_temp',default=95,      help='(requires github.com/mjmvisser/adl3) temperature at which to skip kernel execution, in C, default=95', type='float')
group.add_option('--cutoff_interval',     dest='cutoff_interval',default=0.01, help='(requires adl3) how long to not execute calculations if CUTOFF_TEMP is reached, in seconds, default=0.01', type='float')
group.add_option('--no-server-failbacks', dest='nsf',        action='store_true', help='disable using failback hosts provided by server')
parser.add_option_group(group)

group = OptionGroup(parser, "OpenCL Options", "Every option except 'platform' can be specified as a comma separated list.")
group.add_option('-p', '--platform', dest='platform',   default=-1,          help='use platform by id', type='int')
group.add_option('-d', '--device',   dest='device',     default=[],          help='device ID, by default will use all GPU devices')
group.add_option('-w', '--worksize', dest='worksize',   default=[],          help='work group size, default is maximum returned by OpenCL')
group.add_option('-f', '--frames',   dest='frames',     default=[],          help='will try to bring single kernel execution to 1/frames seconds, default=30, increase this for less desktop lag')
group.add_option('-s', '--sleep',    dest='frameSleep', default=[],          help='sleep per frame in seconds, default 0')
group.add_option('-v', '--vectors',  dest='vectors',    default=[],          help='use vectors, default false')
parser.add_option_group(group)

(options, options.servers) = parser.parse_args()

log.verbose = options.verbose
log.quiet = options.quiet

options.rate = if_else(options.verbose, max(options.rate, 60), max(options.rate, 0.1))

options.version = VERSION

options.max_update_time = 60

platforms = cl.get_platforms()

if options.platform >= len(platforms) or (options.platform == -1 and len(platforms) > 1):
	print 'Wrong platform or more than one OpenCL platforms found, use --platform to select one of the following\n'
	for i in xrange(len(platforms)):
		print '[%d]\t%s' % (i, platforms[i].name)
	sys.exit()

if options.platform == -1:
	options.platform = 0

devices = platforms[options.platform].get_devices()

options.device = tokenize(options.device, 'device')
options.worksize = tokenize(options.worksize, 'worksize')
options.frames = tokenize(options.frames, 'frames')
options.frameSleep = tokenize(options.frameSleep, 'frameSleep', float)
options.vectors = tokenize(options.vectors, 'vectors', bool)

if not options.device:
	for i in xrange(len(devices)):
		print '[%d]\t%s' % (i, devices[i].name)
	print '\nNo devices specified, using all GPU devices\n'

miners = [
	BitcoinMiner(i, options)
	for i in xrange(len(devices))
	if (
		(not options.device and devices[i].type == cl.device_type.GPU) or
		(i in options.device)
	)
]

for i in xrange(len(miners)):
	if i < len(options.worksize):
		miners[i].worksize = options.worksize[i]
	if i < len(options.frames):
		miners[i].frames = options.frames[i]
	if i < len(options.frameSleep):
		miners[i].frameSleep = options.frameSleep[i]
	if i < len(options.vectors):
		miners[i].vectors = options.vectors[i]

servers = None
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

	servers = Servers.Servers(options)

	for miner in miners:
		servers.add_miner(miner)
		miner.start()

	servers.loop()
except KeyboardInterrupt:
	print '\nbye'
finally:
	for miner in miners:
		miner.stop()
	if servers: servers.stop()

	#adl shutdown
	try:
		ADL_OK
		ADL_Main_Control_Destroy()
	except NameError:
		pass
	#end adl shutdown
sleep(1.1)