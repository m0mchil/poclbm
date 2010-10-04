#!/usr/bin/python

import sys
import numpy as np
import pyopencl as cl

from struct import *
from time import sleep, time
from jsonrpc import ServiceProxy
from optparse import OptionParser
from jsonrpc.proxy import JSONRPCException

parser = OptionParser()
parser.add_option('-u', '--user',     dest='user',     default='bitcoin',   help='user name')
parser.add_option('--pass',           dest='password', default='password',  help='password')
parser.add_option('-o', '--host',     dest='host',     default='127.0.0.1', help='RPC host')
parser.add_option('-p', '--port',     dest='port',     default='8332',      help='RPC port')
(options, args) = parser.parse_args()

platform = cl.get_platforms()[0]
devices = platform.get_devices(cl.device_type.GPU)
##context = create_some_context()
context = cl.Context(devices, None, None)
queue = cl.CommandQueue(context)

kernelFile = open('btc_miner.cl', 'r')
miner = cl.Program(context, kernelFile.read()).build()
kernelFile.close()

WORK_GROUP_SIZE = 0
for device in devices:
	WORK_GROUP_SIZE += miner.search.get_work_group_info(cl.kernel_work_group_info.WORK_GROUP_SIZE, device)

globalThreads = WORK_GROUP_SIZE * 33280 #set to less if desktop lags
localThreads  = WORK_GROUP_SIZE

bitcoin = ServiceProxy('http://' + options.user + ':' + options.password + '@' + options.host + ':' + options.port)

work = {}
work['extraNonce'] = 0
work['block'] = ''

output = np.zeros(2, np.uint32)

while True:
	try:
		work = bitcoin.getwork(work['extraNonce'], work['block'])
	except JSONRPCException, e:
		sys.stdout.write('\r                                        \r%s' % e.error['message'])
		sys.stdout.flush()
		sleep(2)
		continue
	except IOError:
		sys.stdout.write('\r                                        \rUnable to communicate with bitcoin RPC')
		sys.stdout.flush()
		sleep(2)
		continue

	try:
		block2 = np.array(unpack('IIIIIIIIIIIIIIII', work['block'][128:].decode('hex')), dtype=np.uint32)
		state  = np.array(unpack('IIIIIIII',         work['state'].decode('hex')),       dtype=np.uint32)
		target = np.array(unpack('IIIIIIII',         work['target'].decode('hex')),      dtype=np.uint32)
	except:
		print '\nWrong data format from RPC!'
		sys.exit()

	output[0] = base = 0

	mf = cl.mem_flags
	block2_buf = cl.Buffer(context, mf.READ_ONLY  | mf.USE_HOST_PTR, hostbuf=block2)
	state_buf  = cl.Buffer(context, mf.READ_ONLY  | mf.USE_HOST_PTR, hostbuf=state)
	target_buf = cl.Buffer(context, mf.READ_ONLY  | mf.USE_HOST_PTR, hostbuf=target)
	output_buf = cl.Buffer(context, mf.WRITE_ONLY | mf.USE_HOST_PTR, hostbuf=output)
	
	start = time()
	while True:
		if (output[0]):
			print '\rfound: ' + output[1] + '                                 '
			work['block'] = work['block'][:152] + pack('I', int(output[1])).encode('hex') + work['block'][160:]
			break

		if (time() - start > 10 or base + globalThreads == 0xFFFFFFFF):
			break

		base += globalThreads
		if (base + globalThreads > 0xFFFFFFFF):
			base = 0xFFFFFFFF - globalThreads

		miner.search(queue, (globalThreads, ), (localThreads, ), block2_buf, state_buf, target_buf, output_buf, pack('I', base))
		cl.enqueue_read_buffer(queue, output_buf, output).wait()
		
		if ((base / globalThreads) % 10 == 0):
			sys.stdout.write('\r                                        \r%s khash/s' % int((base / (time() - start)) / 1000))
			sys.stdout.flush()