from Miner import Miner
from Queue import Empty
from hashlib import md5
from log import say_line
from sha256 import partial, calculateF
from struct import pack
from threading import Lock
from time import sleep, time
from util import if_else, uint32, Object, bytereverse, patch, tokenize
import numpy as np
import sys


PYOPENCL = False
OPENCL = False
ADL = False


try:
	import pyopencl as cl
	PYOPENCL = True
except ImportError:
	print '\nNo PyOpenCL\n'

if PYOPENCL:
	try:
		platforms = cl.get_platforms()
		if len(platforms):
			OPENCL = True
		else:
			print '\nNo OpenCL platforms\n'
	except Exception:
		print '\nNo OpenCL\n'

def has_amd():
	for platform in cl.get_platforms():
		if 'amd' in platform.name.lower():
			return True
	return False

if OPENCL:
	try:
		from adl3 import ADL_Main_Control_Create, ADL_Main_Memory_Alloc, ADL_Main_Control_Destroy, \
			ADLTemperature, ADL_Overdrive5_Temperature_Get, ADL_Adapter_NumberOfAdapters_Get, \
			AdapterInfo, LPAdapterInfo, ADL_Adapter_AdapterInfo_Get, ADL_Adapter_ID_Get, \
			ADL_OK
		from ctypes import sizeof, byref, c_int, cast
		from collections import namedtuple
		if ADL_Main_Control_Create(ADL_Main_Memory_Alloc, 1) != ADL_OK:
			print "\nCouldn't initialize ADL interface.\n"
		else:
			ADL = True
			adl_lock = Lock()
	except ImportError:
		if has_amd():
			print '\nWARNING: no adl3 module found (github.com/mjmvisser/adl3), temperature control is disabled\n'
	except OSError:# if no ADL is present i.e. no AMD platform
		print '\nWARNING: ADL missing (no AMD platform?), temperature control is disabled\n'
else:
	print "\nNot using OpenCL\n"

def shutdown():
	if ADL:
		ADL_Main_Control_Destroy()


def initialize(options):
	if not OPENCL:
		return []

	options.worksize = tokenize(options.worksize, 'worksize')
	options.frames = tokenize(options.frames, 'frames', [30])
	options.frameSleep = tokenize(options.frameSleep, 'frameSleep', cast=float)
	options.vectors = if_else(options.old_vectors, [True], tokenize(options.vectors, 'vectors', [False], bool))

	platforms = cl.get_platforms()

	if options.platform >= len(platforms) or (options.platform == -1 and len(platforms) > 1):
		print 'Wrong platform or more than one OpenCL platforms found, use --platform to select one of the following\n'
		for i in xrange(len(platforms)):
			print '[%d]\t%s' % (i, platforms[i].name)
		sys.exit()

	if options.platform == -1:
		options.platform = 0

	devices = platforms[options.platform].get_devices()

	if not options.device and devices:
		print '\nOpenCL devices:\n'
		for i in xrange(len(devices)):
			print '[%d]\t%s' % (i, devices[i].name)
		print '\nNo devices specified, using all GPU devices\n'

	miners = [
		OpenCLMiner(i, options)
		for i in xrange(len(devices))
		if (
			(not options.device and devices[i].type == cl.device_type.GPU) or
			(i in options.device)
		)
	]

	for i in xrange(len(miners)):
		miners[i].worksize = options.worksize[min(i, len(options.worksize) - 1)]
		miners[i].frames = options.frames[min(i, len(options.frames) - 1)]
		miners[i].frameSleep = options.frameSleep[min(i, len(options.frameSleep) - 1)]
		miners[i].vectors = options.vectors[min(i, len(options.vectors) - 1)]
		miners[i].cutoff_temp = options.cutoff_temp[min(i, len(options.cutoff_temp) - 1)]
		miners[i].cutoff_interval = options.cutoff_interval[min(i, len(options.cutoff_interval) - 1)]
	return miners


class OpenCLMiner(Miner):
	def __init__(self, device_index, options):
		super(OpenCLMiner, self).__init__(device_index, options)
		self.output_size = 0x100

		self.device = cl.get_platforms()[options.platform].get_devices()[device_index]
		self.device_name = self.device.name.strip('\r\n \x00\t')
		self.frames = 30

		self.worksize = self.frameSleep= self.rate = self.estimated_rate = 0
		self.vectors = False

		self.adapterIndex = None
		if ADL and 'amd' in self.device.platform.name.lower() and self.device.type == cl.device_type.GPU:
			with adl_lock:
				self.adapterIndex = self.get_adapter_info()[self.device_index].iAdapterIndex

	def id(self):
		return str(self.options.platform) + ':' + str(self.device_index) + ':' + self.device_name

	def nonce_generator(self, nonces):
		for i in xrange(self.output_size):
			if nonces[i]:
				yield nonces[i]
		

	def mining_thread(self):
		say_line('started OpenCL miner on platform %d, device %d (%s)', (self.options.platform, self.device_index, self.device_name))

		(self.defines, rate_divisor, hashspace) = if_else(self.vectors, ('-DVECTORS', 500, 0x7FFFFFFF), ('', 1000, 0xFFFFFFFF))
		self.defines += (' -DOUTPUT_SIZE=' + str(self.output_size))
		self.defines += (' -DOUTPUT_MASK=' + str(self.output_size - 1))

		self.load_kernel()
		frame = 1.0 / max(self.frames, 3)
		unit = self.worksize * 256
		global_threads = unit * 10

		queue = cl.CommandQueue(self.context)

		last_rated_pace = last_rated = last_n_time = last_temperature = time()
		base = last_hash_rate = threads_run_pace = threads_run = 0
		output = np.zeros(self.output_size + 1, np.uint32)
		output_buffer = cl.Buffer(self.context, cl.mem_flags.WRITE_ONLY | cl.mem_flags.USE_HOST_PTR, hostbuf=output)
		self.kernel.set_arg(20, output_buffer)

		work = None
		temperature = 0
		while True:
			if self.should_stop: return

			sleep(self.frameSleep)

			if (not work) or (not self.work_queue.empty()):
				try:
					work = self.work_queue.get(True, 1)
				except Empty: continue
				else:
					if not work: continue
					nonces_left = hashspace
					state = work.state
					state2 = work.state2
					f = work.f

					self.kernel.set_arg(0, state[0])
					self.kernel.set_arg(1, state[1])
					self.kernel.set_arg(2, state[2])
					self.kernel.set_arg(3, state[3])
					self.kernel.set_arg(4, state[4])
					self.kernel.set_arg(5, state[5])
					self.kernel.set_arg(6, state[6])
					self.kernel.set_arg(7, state[7])

					self.kernel.set_arg(8, state2[1])
					self.kernel.set_arg(9, state2[2])
					self.kernel.set_arg(10, state2[3])
					self.kernel.set_arg(11, state2[5])
					self.kernel.set_arg(12, state2[6])
					self.kernel.set_arg(13, state2[7])

					self.kernel.set_arg(15, f[0])
					self.kernel.set_arg(16, f[1])
					self.kernel.set_arg(17, f[2])
					self.kernel.set_arg(18, f[3])
					self.kernel.set_arg(19, f[4])

			if temperature < self.cutoff_temp:
				self.kernel.set_arg(14, pack('I', base))
				cl.enqueue_nd_range_kernel(queue, self.kernel, (global_threads,), (self.worksize,))

				nonces_left -= global_threads
				threads_run_pace += global_threads
				threads_run += global_threads
				base = uint32(base + global_threads)
			else:
				threads_run_pace = 0
				last_rated_pace = time()
				sleep(self.cutoff_interval)

			now = time()
			if self.adapterIndex != None:
				t = now - last_temperature
				if temperature >= self.cutoff_temp or t > 1:
					last_temperature = now
					with adl_lock:
						temperature = self.get_temperature()

			t = now - last_rated_pace
			if t > 1:
				rate = (threads_run_pace / t) / rate_divisor
				last_rated_pace = now; threads_run_pace = 0
				r = last_hash_rate / rate
				if r < 0.9 or r > 1.1:
					global_threads = max(unit * int((rate * frame * rate_divisor) / unit), unit)
					last_hash_rate = rate

			t = now - last_rated
			if t > self.options.rate:
				self.update_rate(now, threads_run, t, work.targetQ, rate_divisor)
				last_rated = now; threads_run = 0

			queue.finish()
			cl.enqueue_read_buffer(queue, output_buffer, output)
			queue.finish()

			if output[self.output_size]:
				result = Object()
				result.header = work.header
				result.merkle_end = work.merkle_end
				result.time = work.time
				result.difficulty = work.difficulty
				result.target = work.target
				result.state = np.array(state)
				result.nonces = np.array(output)
				result.job_id = work.job_id
				result.extranonce2 = work.extranonce2
				result.server = work.server
				result.miner = self
				self.switch.put(result)
				output.fill(0)
				cl.enqueue_write_buffer(queue, output_buffer, output)

			if not self.switch.update_time:
				if nonces_left < 3 * global_threads * self.frames:
					self.update = True
					nonces_left += 0xFFFFFFFFFFFF
				elif 0xFFFFFFFFFFF < nonces_left < 0xFFFFFFFFFFFF:
					say_line('warning: job finished, %s is idle', self.id()) 
					work = None
			elif now - last_n_time > 1:
				work.time = bytereverse(bytereverse(work.time) + 1)
				state2 = partial(state, work.merkle_end, work.time, work.difficulty, f)
				calculateF(state, work.merkle_end, work.time, work.difficulty, f, state2)
				self.kernel.set_arg(8, state2[1])
				self.kernel.set_arg(9, state2[2])
				self.kernel.set_arg(10, state2[3])
				self.kernel.set_arg(11, state2[5])
				self.kernel.set_arg(12, state2[6])
				self.kernel.set_arg(13, state2[7])
				self.kernel.set_arg(15, f[0])
				self.kernel.set_arg(16, f[1])
				self.kernel.set_arg(17, f[2])
				self.kernel.set_arg(18, f[3])
				self.kernel.set_arg(19, f[4])
				last_n_time = now
				self.update_time_counter += 1
				if self.update_time_counter >= self.switch.max_update_time:
					self.update = True
					self.update_time_counter = 1

	def load_kernel(self):
		self.context = cl.Context([self.device], None, None)
		if (self.device.extensions.find('cl_amd_media_ops') != -1):
			self.defines += ' -DBITALIGN'
			if self.device_name in ['Cedar',
									'Redwood',
									'Juniper',
									'Cypress',
									'Hemlock',
									'Caicos',
									'Turks',
									'Barts',
									'Cayman',
									'Antilles',
									'Wrestler',
									'Zacate',
									'WinterPark',
									'BeaverCreek']:
				self.defines += ' -DBFI_INT'

		kernel_file = open('phatk.cl', 'r')
		kernel = kernel_file.read()
		kernel_file.close()
		m = md5(); m.update(''.join([self.device.platform.name, self.device.platform.version, self.device.name, self.defines, kernel]))
		cache_name = '%s.elf' % m.hexdigest()
		binary = None
		try:
			binary = open(cache_name, 'rb')
			self.program = cl.Program(self.context, [self.device], [binary.read()]).build(self.defines)
		except (IOError, cl.LogicError):
			self.program = cl.Program(self.context, kernel).build(self.defines)
			if (self.defines.find('-DBFI_INT') != -1):
				patchedBinary = patch(self.program.binaries[0])
				self.program = cl.Program(self.context, [self.device], [patchedBinary]).build(self.defines)
			binaryW = open(cache_name, 'wb')
			binaryW.write(self.program.binaries[0])
			binaryW.close()
		finally:
			if binary: binary.close()

		self.kernel = self.program.search

		if not self.worksize:
			self.worksize = self.kernel.get_work_group_info(cl.kernel_work_group_info.WORK_GROUP_SIZE, self.device)

	def get_temperature(self):
		temperature = ADLTemperature()
		temperature.iSize = sizeof(temperature)

		if ADL_Overdrive5_Temperature_Get(self.adapterIndex, 0, byref(temperature)) == ADL_OK:
			return temperature.iTemperature/1000.0
		return 0

	def get_adapter_info(self):
		adapter_info = []
		num_adapters = c_int(-1)
		if ADL_Adapter_NumberOfAdapters_Get(byref(num_adapters)) != ADL_OK:
			say_line("ADL_Adapter_NumberOfAdapters_Get failed, cutoff temperature disabled for %s", self.id())
			return

		AdapterInfoArray = (AdapterInfo * num_adapters.value)()

		if ADL_Adapter_AdapterInfo_Get(cast(AdapterInfoArray, LPAdapterInfo), sizeof(AdapterInfoArray)) != ADL_OK:
			say_line("ADL_Adapter_AdapterInfo_Get failed, cutoff temperature disabled for %s", self.id())
			return

		deviceAdapter = namedtuple('DeviceAdapter', ['AdapterIndex', 'AdapterID', 'BusNumber', 'UDID'])
		devices = []

		for adapter in AdapterInfoArray:
			index = adapter.iAdapterIndex
			busNum = adapter.iBusNumber
			udid = adapter.strUDID

			adapterID = c_int(-1)

			if ADL_Adapter_ID_Get(index, byref(adapterID)) != ADL_OK:
				say_line("ADL_Adapter_Active_Get failed, cutoff temperature disabled for %s", self.id())
				return

			found = False
			for device in devices:
				if (device.AdapterID.value == adapterID.value):
					found = True
					break

			if (found == False):
				devices.append(deviceAdapter(index, adapterID, busNum, udid))

		for device in devices:
			adapter_info.append(AdapterInfoArray[device.AdapterIndex])

		return adapter_info
