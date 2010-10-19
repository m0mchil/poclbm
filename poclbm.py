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


def uint32(x):
	return x & 0xffffffffL
def rot(x, y):
	return (x<<y | x>>(32-y))
def sharound(a,b,c,d,e,f,g,h,x,K):
	t1=h+(rot(e, 26)^rot(e, 21)^rot(e, 7))+(g^(e&(f^g)))+K+x
	t2=(rot(a, 30)^rot(a, 19)^rot(a, 10))+((a&b)|(c&(a|b)))
	return (uint32(d + t1), uint32(t1+t2))

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
(options, args) = parser.parse_args()
options.frames = max(options.frames, 1.1)
options.askrate = max(options.askrate, 1)
options.askrate = min(options.askrate, 30)

platform = cl.get_platforms()[0]
if (options.device != -1):
	devices = platform.get_devices()
	context = cl.Context([devices[options.device]], None, None)
else:
	print 'No device specified, you may use -d to specify one of the following\n'
	context = cl.create_some_context()
queue = cl.CommandQueue(context)
defines = ''
if (platform.name.lower().find('nvidia') != -1):
	defines = '-DNVIDIA'
kernelFile = open('btc_miner.cl', 'r')
miner = cl.Program(context, kernelFile.read()).build(defines)
kernelFile.close()

if (options.worksize == -1):
	options.worksize = miner.search.get_work_group_info(cl.kernel_work_group_info.WORK_GROUP_SIZE, context.devices[0])

frames = options.frames
frame = float(1)/frames
window = frame/30
upper = frame + window
lower = frame - window

unit = options.worksize * 256
globalThreads = unit

bitcoin = ServiceProxy('http://' + options.user + ':' + options.password + '@' + options.host + ':' + options.port)

work = {}
work['extraNonce'] = 0
work['block'] = ''
output = np.zeros(2, np.uint32)

threadsRun = 0
rate = time()

while True:
	try:
		work = bitcoin.getwork(work['extraNonce'], work['block'])
	except JSONRPCException, e:
		sysWrite('%s', e.error['message'])
		sleep(2)
		continue
	except IOError:
		sysWrite('Unable to communicate with bitcoin RPC')
		sleep(2)
		continue

	try:
		block2 = np.array(unpack('IIIIIIIIIIIIIIII', work['block'][128:].decode('hex')), dtype=np.uint32)
		state  = np.array(unpack('IIIIIIII',         work['state'].decode('hex')),       dtype=np.uint32)
		target = np.array(unpack('IIIIIIII',         work['target'].decode('hex')),      dtype=np.uint32)
	except:
		sysWriteLn('Wrong data format from RPC!')
		sys.exit()

	if (target[6] == 0):
		sysWriteLn('Check if kernel does all sha256 rounds!')
	
	state2 = np.array(state)
	(state2[3], state2[7]) = sharound(state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],state2[6],state2[7],block2[0],0x428A2F98)
	(state2[2], state2[6]) = sharound(state2[7],state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],state2[6],block2[1],0x71374491)
	(state2[1], state2[5]) = sharound(state2[6],state2[7],state2[0],state2[1],state2[2],state2[3],state2[4],state2[5],block2[2],0xB5C0FBCF)

	output[0] = base = 0
	output_buf = cl.Buffer(context, cl.mem_flags.WRITE_ONLY | cl.mem_flags.USE_HOST_PTR, hostbuf=output)

	start = time()
	while True:
		if (output[0]):
			work['block'] = work['block'][:152] + pack('I', long(output[1])).encode('hex') + work['block'][160:]
			sysWriteLn('found: %s, %s', (output[1], datetime.now().strftime("%d/%m/%Y %H:%M")))
			break

		if (time() - start > options.askrate or base + globalThreads == 0x7FFFFFFF):
			break

		base += globalThreads
		if (base + globalThreads > 0x7FFFFFFF):
			base = 0x7FFFFFFF - globalThreads

		kernelStart = time()
		miner.search(	queue, (globalThreads, ), (options.worksize, ),
						block2[0], block2[1], block2[2],
						state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7],
						state2[1], state2[2], state2[3], state2[5], state2[6], state2[7],
						target[6], pack('I', base), output_buf)
		cl.enqueue_read_buffer(queue, output_buf, output).wait()
		kernelTime = time() - kernelStart
		threadsRun += globalThreads

		if (kernelTime < lower):
			globalThreads += unit
		elif (kernelTime > upper and globalThreads != unit):
			globalThreads -= unit

		if (time() - rate > options.rate):
			sysWrite('%s khash/s', int((threadsRun / (time() - rate)) / 500))
			threadsRun = 0
			rate = time()