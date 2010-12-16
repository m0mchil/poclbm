import sys
import numpy as np
import pyopencl as cl

from struct import *
from time import sleep, time
from datetime import datetime
from jsonrpc import ServiceProxy
from jsonrpc.proxy import JSONRPCException
from jsonrpc.json import JSONDecodeException


def uint32(x):
	return x & 0xffffffffL

def rot(x, y):
	return (x<<y | x>>(32-y))
	
def sharound(a,b,c,d,e,f,g,h,x,K):
	t1=h+(rot(e, 26)^rot(e, 21)^rot(e, 7))+(g^(e&(f^g)))+K+x
	t2=(rot(a, 30)^rot(a, 19)^rot(a, 10))+((a&b)|(c&(a|b)))
	return (uint32(d + t1), uint32(t1+t2))

def partial(state, data):
	partial = np.array(state)
	(partial[3], partial[7]) = sharound(partial[0],partial[1],partial[2],partial[3],partial[4],partial[5],partial[6],partial[7],data[0],0x428A2F98)
	(partial[2], partial[6]) = sharound(partial[7],partial[0],partial[1],partial[2],partial[3],partial[4],partial[5],partial[6],data[1],0x71374491)
	(partial[1], partial[5]) = sharound(partial[6],partial[7],partial[0],partial[1],partial[2],partial[3],partial[4],partial[5],data[2],0xB5C0FBCF)
	return partial

def if_else(condition, trueVal, falseVal):
	if condition:
		return trueVal
	else:
		return falseVal

def bytereverse(x):
	return uint32(( ((x) << 24) | (((x) << 8) & 0x00ff0000) | (((x) >> 8) & 0x0000ff00) | ((x) >> 24) ))

class BitcoinMiner:
	def __init__(self, platform, context, host, user, password, port=8332, frames=60, rate=1, askrate=5, worksize=-1, vectors=False):
		(defines, self.rateDivisor) = if_else(vectors, ('-DVECTORS', 500), ('', 1000))

		self.context = context
		self.rate = float(rate)
		self.askrate = int(askrate)
		self.worksize = int(worksize)

		if (self.context.devices[0].extensions.find('cl_amd_media_ops') != -1):
			defines += ' -DBITALIGN'
			
		kernelFile = open('BitcoinMiner.cl', 'r')
		self.miner = cl.Program(self.context, kernelFile.read()).build(defines)
		kernelFile.close()

		if (self.worksize == -1):
			self.worksize = self.miner.search.get_work_group_info(cl.kernel_work_group_info.WORK_GROUP_SIZE, self.context.devices[0])

		frame = float(1)/float(frames)
		window = frame/30
		self.upper = frame + window
		self.lower = frame - window

		self.unit = self.worksize * 256
		self.globalThreads = self.unit

		self.bitcoin = ServiceProxy('http://%s:%s@%s:%s' % (user, password, host, port))

	def say(self, format, args=()):
		sys.stdout.write('\r                                        \r' + format % args)
		sys.stdout.flush()

	def sayLine(self, format, args=()):
		self.say(format + '\n', args)

	def blockFound(self, hash, accepted):
		# designed to be overridden
		self.sayLine('%s, %s, %s', (datetime.now().strftime("%d/%m/%Y %H:%M"), hash, if_else(accepted, 'accepted', 'invalid or stale')))
	
	def mine(self):
		work = {}
		output = np.zeros(2, np.uint32)
		output_buf = cl.Buffer(self.context, cl.mem_flags.WRITE_ONLY | cl.mem_flags.USE_HOST_PTR, hostbuf=output)

		queue = cl.CommandQueue(self.context)

		base = threadsRun = 0
		lastRate = time()
		while True:
			try:
				work.clear()
				work = self.bitcoin.getwork()
			except JSONRPCException, e:
				self.say('%s', e.error['message'])
			except (JSONDecodeException, IOError):
				self.say('Problems communicating with bitcoin RPC')
			if not work:
				sleep(2)
				continue
			
			try:
				data   = np.array(unpack('IIIIIIIIIIIIIIII', work['data'][128:].decode('hex')), dtype=np.uint32)
				state  = np.array(unpack('IIIIIIII',         work['midstate'].decode('hex')),   dtype=np.uint32)
				target = np.array(unpack('IIIIIIII',         work['target'].decode('hex')),     dtype=np.uint32)
			except:
				self.sayLine('Wrong data format from RPC!')
				sys.exit()

			state2 = partial(state, data)

			start = lastNTime = time()
			while True:
				if (output[0]):
					work['data'] = work['data'][:136] + pack('I', long(data[1])).encode('hex') + work['data'][144:152] + pack('I', long(output[1])).encode('hex') + work['data'][160:]
					try:
						result = self.bitcoin.getwork(work['data'])
					except (StandardError, JSONDecodeException) as e:
						self.sayLine(str(e))
						self.sayLine('Solution lost!')
					else:
						self.blockFound(pack('I', long(output[0])).encode('hex'), result)
					output[0] = 0
					cl.enqueue_write_buffer(queue, output_buf, output)
					break

				if (time() - start > self.askrate):
					break

				if (time() - lastNTime > 1):
					data[1] = bytereverse(bytereverse(data[1]) + 1)
					state2 = partial(state, data)
					lastNTime = time()

				base = uint32(base + self.globalThreads)
				kernelStart = time()
				self.miner.search(	queue, (self.globalThreads, ), (self.worksize, ),
									data[0], data[1], data[2],
									state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7],
									state2[1], state2[2], state2[3], state2[5], state2[6], state2[7],
									target[6], target[7], pack('I', base), output_buf)
				cl.enqueue_read_buffer(queue, output_buf, output)
				queue.finish()
				kernelTime = time() - kernelStart
				threadsRun += self.globalThreads

				if (kernelTime < self.lower):
					self.globalThreads += self.unit
				elif (kernelTime > self.upper and self.globalThreads > self.unit):
					self.globalThreads -= self.unit

				if (time() - lastRate > self.rate):
					self.say('%s khash/s', int((threadsRun / (time() - lastRate)) / self.rateDivisor))
					threadsRun = 0
					lastRate = time()