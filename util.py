from log import say_exception
import sys

class Object(object):
	pass

def uint32(x):
	return x & 0xffffffffL

def bytereverse(x):
	return uint32(( ((x) << 24) | (((x) << 8) & 0x00ff0000) | (((x) >> 8) & 0x0000ff00) | ((x) >> 24) ))

def bytearray_to_uint32(x):
	return uint32(((x[3]) << 24) | ((x[2]) << 16)  | ((x[1]) << 8) | x[0])

def belowOrEquals(hash_, target):
	for i in xrange(len(hash_) - 1, -1, -1):
		reversed_ = bytereverse(hash_[i])
		if reversed_ < target[i]:
			return True
		elif reversed_ > target[i]:
			return False
	return True

def chunks(l, n):
	for i in xrange(0, len(l), n):
		yield l[i:i+n]

def tokenize(option, name, default=[0], cast=int):
	if option:
		try:
			return [cast(x) for x in option.split(',')]
		except ValueError:
			say_exception('Invalid %s(s) specified: %s\n\n' % (name, option))
			sys.exit()
	return default
