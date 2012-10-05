from util import uint32
import numpy as np

K = np.array(	[0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
				0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
				0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
				0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
				0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
				0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
				0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
				0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2], np.uint32)

STATE = np.array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19], np.uint32)

def rotr(x, y):
	return (x>>y | x<<(32-y))

def rot(x, y):
	return (x<<y | x>>(32-y))

def R(x2, x7, x15, x16):
	return uint32((rot(x2,15)^rot(x2,13)^((x2)>>10)) + x7 + (rot(x15,25)^rot(x15,14)^((x15)>>3)) + x16)

def sharound(a,b,c,d,e,f,g,h,x,K):
	t1=h+(rot(e, 26)^rot(e, 21)^rot(e, 7))+(g^(e&(f^g)))+K+x
	t2=(rot(a, 30)^rot(a, 19)^rot(a, 10))+((a&b)|(c&(a|b)))
	return (uint32(d + t1), uint32(t1+t2))

def partial(state, merkle_end, time, difficulty, f):
	state2 = np.array(state)
	data = [merkle_end, time, difficulty]
	for i in xrange(3):
		(state2[~(i-4)&7], state2[~(i-8)&7]) = sharound(state2[(~(i-1)&7)],state2[~(i-2)&7],state2[~(i-3)&7],state2[~(i-4)&7],state2[~(i-5)&7],state2[~(i-6)&7],state2[~(i-7)&7],state2[~(i-8)&7],data[i],K[i])

	f[0] = uint32(data[0] + (rotr(data[1], 7) ^ rotr(data[1], 18) ^ (data[1] >> 3)))
	f[1] = uint32(data[1] + (rotr(data[2], 7) ^ rotr(data[2], 18) ^ (data[2] >> 3)) + 0x01100000)
	f[2] = uint32(data[2] + (rotr(f[0], 17) ^ rotr(f[0], 19) ^ (f[0] >> 10)))
	f[3] = uint32(0x11002000 + (rotr(f[1], 17) ^ rotr(f[1], 19) ^ (f[1] >> 10)))
	f[4] = uint32(0x00000280 + (rotr(f[0], 7) ^ rotr(f[0], 18) ^ (f[0] >> 3)))
	f[5] = uint32(f[0] + (rotr(f[1], 7) ^ rotr(f[1], 18) ^ (f[1] >> 3)))
	f[6] = uint32(state[4] + (rotr(state2[1], 6) ^ rotr(state2[1], 11) ^ rotr(state2[1], 25)) + (state2[3] ^ (state2[1] & (state2[2] ^ state2[3]))) + 0xe9b5dba5)
	f[7] = uint32((rotr(state2[5], 2) ^ rotr(state2[5], 13) ^ rotr(state2[5], 22)) + ((state2[5] & state2[6]) | (state2[7] & (state2[5] | state2[6]))))
	return state2

def calculateF(state, merkle_end, time, difficulty, f, state2):
		data = [merkle_end, time, difficulty]
		rot = lambda x,y: x>>y | x<<(32-y)
		#W2
		f[0] = np.uint32(data[2])

		#W16
		f[1] = np.uint32(data[0] + (rot(data[1], 7) ^ rot(data[1], 18) ^
			(data[1] >> 3)))
		#W17
		f[2] = np.uint32(data[1] + (rot(data[2], 7) ^ rot(data[2], 18) ^
			(data[2] >> 3)) + 0x01100000)

		#2 parts of the first SHA round
		f[3] = np.uint32(state[4] + (rot(state2[1], 6) ^
			rot(state2[1], 11) ^ rot(state2[1], 25)) +
			(state2[3] ^ (state2[1] & (state2[2] ^
			state2[3]))) + 0xe9b5dba5)
		f[4] = np.uint32((rot(state2[5], 2) ^
			rot(state2[5], 13) ^ rot(state2[5], 22)) +
			((state2[5] & state2[6]) | (state2[7] &
			(state2[5] | state2[6]))))

def sha256(state, data):
	digest = np.copy(state)
	for i in xrange(64):
		if i > 15:
			data[i] = R(data[i-2], data[i-7], data[i-15], data[i-16])
		(digest[~(i-4)&7], digest[~(i-8)&7]) = sharound(digest[(~(i-1)&7)],digest[~(i-2)&7],digest[~(i-3)&7],digest[~(i-4)&7],digest[~(i-5)&7],digest[~(i-6)&7],digest[~(i-7)&7],digest[~(i-8)&7],data[i],K[i])
	return np.add(digest, state)

def hash(midstate, merkle_end, time, difficulty, nonce):
	work = np.zeros(64, np.uint32)
	work[0]=merkle_end; work[1]=time; work[2]=difficulty; work[3]=nonce
	work[4]=0x80000000; work[5]=0x00000000; work[6]=0x00000000; work[7]=0x00000000
	work[8]=0x00000000; work[9]=0x00000000; work[10]=0x00000000; work[11]=0x00000000
	work[12]=0x00000000; work[13]=0x00000000; work[14]=0x00000000; work[15]=0x00000280

	state = sha256(midstate, work)

	work[0]=state[0]; work[1]=state[1]; work[2]=state[2]; work[3]=state[3]
	work[4]=state[4]; work[5]=state[5]; work[6]=state[6]; work[7]=state[7]
	work[8]=0x80000000; work[15]=0x00000100

	return sha256(STATE, work)
