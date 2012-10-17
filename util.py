from log import say_exception
from struct import pack, unpack, error
import sys

class Object(object):
	pass

def uint32(x):
	return x & 0xffffffffL

def bytereverse(x):
	return uint32(( ((x) << 24) | (((x) << 8) & 0x00ff0000) | (((x) >> 8) & 0x0000ff00) | ((x) >> 24) ))

def belowOrEquals(hash_, target):
	for i in range(len(hash_) - 1, -1, -1):
		reversed_ = bytereverse(hash_[i])
		if reversed_ < target[i]:
			return True
		elif reversed_ > target[i]:
			return False
	return True

def if_else(condition, trueVal, falseVal):
	if condition:
		return trueVal
	else:
		return falseVal

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

def patch(data):
	pos = data.find('\x7fELF', 1)
	if pos != -1 and data.find('\x7fELF', pos+1) == -1:
		data2 = data[pos:]
		try:
			(id, a, b, c, d, e, f, offset, g, h, i, j, entrySize, count, index) = unpack('QQHHIIIIIHHHHHH', data2[:52])
			if id == 0x64010101464c457f and offset != 0:
				(a, b, c, d, nameTableOffset, size, e, f, g, h) = unpack('IIIIIIIIII', data2[offset+index * entrySize : offset+(index+1) * entrySize])
				header = data2[offset : offset+count * entrySize]
				firstText = True
				for i in xrange(count):
					entry = header[i * entrySize : (i+1) * entrySize]
					(nameIndex, a, b, c, offset, size, d, e, f, g) = unpack('IIIIIIIIII', entry)
					nameOffset = nameTableOffset + nameIndex
					name = data2[nameOffset : data2.find('\x00', nameOffset)]
					if name == '.text':
						if firstText: firstText = False
						else:
							data2 = data2[offset : offset + size]
							patched = ''
							for i in xrange(len(data2) / 8):
								instruction, = unpack('Q', data2[i * 8 : i * 8 + 8])
								if (instruction&0x9003f00002001000) == 0x0001a00000000000:
									instruction ^= (0x0001a00000000000 ^ 0x0000c00000000000)
								patched += pack('Q', instruction)
							return ''.join([data[:pos+offset], patched, data[pos + offset + size:]])
		except error:
			pass
	return data
