from Queue import Queue, Empty
from decimal import Decimal
from hashlib import md5
from log import *
from sha256 import *
from struct import pack
from threading import Thread
from time import sleep, time
from util import *
import log
import pyopencl as cl


class BitcoinMiner():
	def __init__(self, device, options, version, transport):
		self.output_size = 0x100
		self.options = options
		self.version = version
		(self.defines, self.rate_divisor, self.hashspace) = if_else(self.options.vectors, ('-DVECTORS', 500, 0x7FFFFFFF), ('', 1000, 0xFFFFFFFF))
		self.defines += (' -DOUTPUT_SIZE=' + str(self.output_size))
		self.defines += (' -DOUTPUT_MASK=' + str(self.output_size - 1))

		self.device = device
		self.options.rate = if_else(self.options.verbose, max(self.options.rate, 60), max(self.options.rate, 0.1))
		self.options.askrate = max(self.options.askrate, 1)
		self.options.askrate = min(self.options.askrate, 10)
		self.options.frames = max(self.options.frames, 3)

		self.update_time = False
		self.share_count = [0, 0]
		self.work_queue = Queue()
		self.transport = transport(self)
		log.verbose = self.options.verbose
		log.quiet = self.options.quiet

	def start(self):
		self.should_stop = False
		Thread(target=self.mining_thread).start()
		self.transport.loop()

	def stop(self):
		self.transport.stop()
		self.should_stop = True


	def say_status(self, rate, estimated_rate):
		rate = Decimal(rate) / 1000
		estimated_rate = Decimal(estimated_rate) / 1000
		total_shares = self.share_count[1] + self.share_count[0]
		total_shares_estimator = max(total_shares, total_shares, 1)
		say_quiet('[%.03f MH/s (~%d MH/s)] [Rej: %d/%d (%.02f%%)]', (rate, round(estimated_rate), self.share_count[0], total_shares, float(self.share_count[0]) * 100 / total_shares_estimator))

	def diff1_found(self, hash, target):
		if self.options.verbose and target < 0xFFFF0000L:
			say_line('checking %s <= %s', (hash, target))

	def share_found(self, hash, accepted, is_block):
		self.share_count[if_else(accepted, 1, 0)] += 1
		if self.options.verbose or is_block:
			say_line('%s%s, %s', (if_else(is_block, 'block ', ''), hash, if_else(accepted, 'accepted', '_rejected_')))

	def mining_thread(self):
		self.load_kernel()
		frame = 1.0 / self.options.frames
		unit = self.options.worksize * 256
		global_threads = unit * 10
		
		queue = cl.CommandQueue(self.context)

		start_time = last_rated_pace = last_rated = last_n_time = time()
		base = last_hash_rate = threads_run_pace = threads_run = 0
		accept_hist = []
		output = np.zeros(self.output_size + 1, np.uint32)
		output_buffer = cl.Buffer(self.context, cl.mem_flags.WRITE_ONLY | cl.mem_flags.USE_HOST_PTR, hostbuf=output)

		work = None
		while True:
		        sleep(self.options.frameSleep)
			if self.should_stop: return
			if (not work) or (not self.work_queue.empty()):
				try:
					work = self.work_queue.get(True, 1)
				except Empty: continue
				else:
					if not work: continue
					nonces_left = self.hashspace
					state = work.state
					state2 = work.state2
					f = work.f

			self.miner.search(queue, (global_threads,), (self.options.worksize,),
								state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7],
								state2[1], state2[2], state2[3], state2[5], state2[6], state2[7],
								pack('I', base),
								f[0], f[1], f[2], f[3], f[4], # f[5], f[6], f[7],
								output_buffer)
			cl.enqueue_read_buffer(queue, output_buffer, output)

			nonces_left -= global_threads
			threads_run_pace += global_threads
			threads_run += global_threads
			base = uint32(base + global_threads)

			now = time()
			t = now - last_rated_pace
			if (t > 1):
				rate = (threads_run_pace / t) / self.rate_divisor
				last_rated_pace = now; threads_run_pace = 0
				r = last_hash_rate / rate
				if r < 0.9 or r > 1.1:
					global_threads = max(unit * int((rate * frame * self.rate_divisor) / unit), unit)
					last_hash_rate = rate
			t = now - last_rated
			if (t > self.options.rate):
				rate = int((threads_run / t) / self.rate_divisor)

				if accept_hist:
					LAH = accept_hist.pop()
					if LAH[1] != self.share_count[1]:
						accept_hist.append(LAH)
				accept_hist.append((now, self.share_count[1]))
				while (accept_hist[0][0] < now - self.options.estimate):
					accept_hist.pop(0)
				new_accept = self.share_count[1] - accept_hist[0][1]
				estimated_rate = Decimal(new_accept) * (work.targetQ) / min(int(now - start_time), self.options.estimate) / 1000

				self.say_status(rate, estimated_rate)
				last_rated = now; threads_run = 0

			queue.finish()

			if output[self.output_size]:
				result = Object()
				result.header = work.header
				result.merkle_end = work.merkle_end
				result.time = work.time
				result.difficulty = work.difficulty
				result.target = work.target
				result.state = np.array(state)
				result.nonce = np.array(output)
				self.transport.result_queue.put(result)
				output.fill(0)
				cl.enqueue_write_buffer(queue, output_buffer, output)

			if not self.update_time:
				if nonces_left < (self.transport.timeout + 1) * global_threads * self.options.frames:
					self.transport.update = True
					nonces_left += 0xFFFFFFFFFFFF
				elif 0xFFFFFFFFFFF < nonces_left < 0xFFFFFFFFFFFF:
					say_line('warning: job finished, miner is idle')
					work = None
			elif now - last_n_time > 1:
				work.time = bytereverse(bytereverse(work.time) + 1)
				state2 = partial(state, work.merkle_end, work.time, work.difficulty, f)
				calculateF(state, work.merkle_end, work.time, work.difficulty, f, state2)
				last_n_time = now

	def load_kernel(self):
		self.context = cl.Context([self.device], None, None)
		if (self.device.extensions.find('cl_amd_media_ops') != -1):
			self.defines += ' -DBITALIGN'
			self.defines += ' -DBFI_INT'

		kernel_file = open('phatk.cl', 'r')
		kernel = kernel_file.read()
		kernel_file.close()
		m = md5(); m.update(''.join([self.device.platform.name, self.device.platform.version, self.device.name, self.defines, kernel]))
		cache_name = '%s.elf' % m.hexdigest()
		binary = None
		try:
			binary = open(cache_name, 'rb')
			self.miner = cl.Program(self.context, [self.device], [binary.read()]).build(self.defines)
		except (IOError, cl.LogicError):
			self.miner = cl.Program(self.context, kernel).build(self.defines)
			if (self.defines.find('-DBITALIGN') != -1):
				patchedBinary = patch(self.miner.binaries[0])
				self.miner = cl.Program(self.context, [self.device], [patchedBinary]).build(self.defines)
			binaryW = open(cache_name, 'wb')
			binaryW.write(self.miner.binaries[0])
			binaryW.close()
		finally:
			if binary: binary.close()

		if (self.options.worksize == -1):
			self.options.worksize = self.miner.search.get_work_group_info(cl.kernel_work_group_info.WORK_GROUP_SIZE, self.device)
