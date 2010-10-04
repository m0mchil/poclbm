__constant uint SHA256_K[64] = 
{
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

#define bytereverse(x) ( ((x) << 24) | (((x) << 8) & 0x00ff0000) | (((x) >> 8) & 0x0000ff00) | ((x) >> 24) )

//#define rotrI(x, y) ( x>>y | x << (32-y) )

#define ChI(x, y, z) ( z ^ (x & ( y ^ z)) )
#define MajI(x, y, z) ( (x & y) | (z & (x | y)) )

/*#define S0I(x) (rotrI(x,2) ^ rotrI(x,13) ^ rotrI(x,22))
#define S1I(x) (rotrI(x,6) ^ rotrI(x,11) ^ rotrI(x,25))
#define s0I(x) (rotrI(x,7) ^ rotrI(x,18) ^ (x>>3))
#define s1I(x) (rotrI(x,17) ^ rotrI(x,19) ^ (x>>10))*/

#define S0I(x) (rotate(x,30) ^ rotate(x,19) ^ rotate(x,10))
#define S1I(x) (rotate(x,26) ^ rotate(x,21) ^ rotate(x,7))
#define s0I(x) (rotate(x,25) ^ rotate(x,14) ^ (x>>3))
#define s1I(x) (rotate(x,15) ^ rotate(x,13) ^ (x>>10))

void sha256_process_block(uint *state,  uint *data)
{
	uint W00,W01,W02,W03,W04,W05,W06,W07;
	uint W08,W09,W10,W11,W12,W13,W14,W15;
	uint T0,T1,T2,T3,T4,T5,T6,T7;
   
	T0 = state[0]; T1 = state[1]; 
	T2 = state[2]; T3 = state[3]; 
	T4 = state[4]; T5 = state[5]; 
	T6 = state[6]; T7 = state[7];

	T7 += S1I( T4 ) + ChI( T4, T5, T6 ) + SHA256_K[0] + ( (W00 = data[0]) );
	T3 += T7;
	T7 += S0I( T0 ) + MajI( T0, T1, T2 );
	
	T6 += S1I( T3 ) + ChI( T3, T4, T5 ) + SHA256_K[1] + ( (W01 = data[1]) );
	T2 += T6;
	T6 += S0I( T7 ) + MajI( T7, T0, T1 );
	
	T5 += S1I( T2 ) + ChI( T2, T3, T4 ) + SHA256_K[2] + ( (W02 = data[2]) );
	T1 += T5;
	T5 += S0I( T6 ) + MajI( T6, T7, T0 );
	
	T4 += S1I( T1 ) + ChI( T1, T2, T3 ) + SHA256_K[3] + ( (W03 = data[3]) );
	T0 += T4;
	T4 += S0I( T5 ) + MajI( T5, T6, T7 );
	
	T3 += S1I( T0 ) + ChI( T0, T1, T2 ) + SHA256_K[4] + ( (W04 = data[4]) );
	T7 += T3;
	T3 += S0I( T4 ) + MajI( T4, T5, T6 );
	
	T2 += S1I( T7 ) + ChI( T7, T0, T1 ) + SHA256_K[5] + ( (W05 = data[5]) );
	T6 += T2;
	T2 += S0I( T3 ) + MajI( T3, T4, T5 );
	
	T1 += S1I( T6 ) + ChI( T6, T7, T0 ) + SHA256_K[6] + ( (W06 = data[6]) );
	T5 += T1;
	T1 += S0I( T2 ) + MajI( T2, T3, T4 );
	
	T0 += S1I( T5 ) + ChI( T5, T6, T7 ) + SHA256_K[7] + ( (W07 = data[7]) );
	T4 += T0;
	T0 += S0I( T1 ) + MajI( T1, T2, T3 );
	
	T7 += S1I( T4 ) + ChI( T4, T5, T6 ) + SHA256_K[8] + ( (W08 = data[8]) );
	T3 += T7;
	T7 += S0I( T0 ) + MajI( T0, T1, T2 );
	
	T6 += S1I( T3 ) + ChI( T3, T4, T5 ) + SHA256_K[9] + ( (W09 = data[9]) );
	T2 += T6;
	T6 += S0I( T7 ) + MajI( T7, T0, T1 );
	
	T5 += S1I( T2 ) + ChI( T2, T3, T4 ) + SHA256_K[10] + ( (W10 = data[10]) );
	T1 += T5;
	T5 += S0I( T6 ) + MajI( T6, T7, T0 );
	
	T4 += S1I( T1 ) + ChI( T1, T2, T3 ) + SHA256_K[11] + ( (W11 = data[11]) );
	T0 += T4;
	T4 += S0I( T5 ) + MajI( T5, T6, T7 );
	
	T3 += S1I( T0 ) + ChI( T0, T1, T2 ) + SHA256_K[12] + ( (W12 = data[12]) );
	T7 += T3;
	T3 += S0I( T4 ) + MajI( T4, T5, T6 );
	
	T2 += S1I( T7 ) + ChI( T7, T0, T1 ) + SHA256_K[13] + ( (W13 = data[13]) );
	T6 += T2;
	T2 += S0I( T3 ) + MajI( T3, T4, T5 );
	
	T1 += S1I( T6 ) + ChI( T6, T7, T0 ) + SHA256_K[14] + ( (W14 = data[14]) );
	T5 += T1;
	T1 += S0I( T2 ) + MajI( T2, T3, T4 );
	
	T0 += S1I( T5 ) + ChI( T5, T6, T7 ) + SHA256_K[15] + ( (W15 = data[15]) );
	T4 += T0;
	T0 += S0I( T1 ) + MajI( T1, T2, T3 );

	
	
	T7 += S1I( T4 ) + ChI( T4, T5, T6 ) + SHA256_K[16] + ( (W00 += s1I( W14 ) + W09 + s0I( W01 ) ) );
	T3 += T7;
	T7 += S0I( T0 ) + MajI( T0, T1, T2 );
	
	T6 += S1I( T3 ) + ChI( T3, T4, T5 ) + SHA256_K[17] + ( (W01 += s1I( W15 ) + W10 + s0I( W02 ) ) );
	T2 += T6;
	T6 += S0I( T7 ) + MajI( T7, T0, T1 );
	
	T5 += S1I( T2 ) + ChI( T2, T3, T4 ) + SHA256_K[18] + ( (W02 += s1I( W00 ) + W11 + s0I( W03 ) ) );
	T1 += T5;
	T5 += S0I( T6 ) + MajI( T6, T7, T0 );
	
	T4 += S1I( T1 ) + ChI( T1, T2, T3 ) + SHA256_K[19] + ( (W03 += s1I( W01 ) + W12 + s0I( W04 ) ) );
	T0 += T4;
	T4 += S0I( T5 ) + MajI( T5, T6, T7 );
	
	T3 += S1I( T0 ) + ChI( T0, T1, T2 ) + SHA256_K[20] + ( (W04 += s1I( W02 ) + W13 + s0I( W05 ) ) );
	T7 += T3;
	T3 += S0I( T4 ) + MajI( T4, T5, T6 );
	
	T2 += S1I( T7 ) + ChI( T7, T0, T1 ) + SHA256_K[21] + ( (W05 += s1I( W03 ) + W14 + s0I( W06 ) ) );
	T6 += T2;
	T2 += S0I( T3 ) + MajI( T3, T4, T5 );
	
	T1 += S1I( T6 ) + ChI( T6, T7, T0 ) + SHA256_K[22] + ( (W06 += s1I( W04 ) + W15 + s0I( W07 ) ) );
	T5 += T1;
	T1 += S0I( T2 ) + MajI( T2, T3, T4 );
	
	T0 += S1I( T5 ) + ChI( T5, T6, T7 ) + SHA256_K[23] + ( (W07 += s1I( W05 ) + W00 + s0I( W08 ) ) );
	T4 += T0;
	T0 += S0I( T1 ) + MajI( T1, T2, T3 );
	
	T7 += S1I( T4 ) + ChI( T4, T5, T6 ) + SHA256_K[24] + ( (W08 += s1I( W06 ) + W01 + s0I( W09 ) ) );
	T3 += T7;
	T7 += S0I( T0 ) + MajI( T0, T1, T2 );
	
	T6 += S1I( T3 ) + ChI( T3, T4, T5 ) + SHA256_K[25] + ( (W09 += s1I( W07 ) + W02 + s0I( W10 ) ) );
	T2 += T6;
	T6 += S0I( T7 ) + MajI( T7, T0, T1 );
	
	T5 += S1I( T2 ) + ChI( T2, T3, T4 ) + SHA256_K[26] + ( (W10 += s1I( W08 ) + W03 + s0I( W11 ) ) );
	T1 += T5;
	T5 += S0I( T6 ) + MajI( T6, T7, T0 );
	
	T4 += S1I( T1 ) + ChI( T1, T2, T3 ) + SHA256_K[27] + ( (W11 += s1I( W09 ) + W04 + s0I( W12 ) ) );
	T0 += T4;
	T4 += S0I( T5 ) + MajI( T5, T6, T7 );
	
	T3 += S1I( T0 ) + ChI( T0, T1, T2 ) + SHA256_K[28] + ( (W12 += s1I( W10 ) + W05 + s0I( W13 ) ) );
	T7 += T3;
	T3 += S0I( T4 ) + MajI( T4, T5, T6 );
	
	T2 += S1I( T7 ) + ChI( T7, T0, T1 ) + SHA256_K[29] + ( (W13 += s1I( W11 ) + W06 + s0I( W14 ) ) );
	T6 += T2;
	T2 += S0I( T3 ) + MajI( T3, T4, T5 );
	
	T1 += S1I( T6 ) + ChI( T6, T7, T0 ) + SHA256_K[30] + ( (W14 += s1I( W12 ) + W07 + s0I( W15 ) ) );
	T5 += T1;
	T1 += S0I( T2 ) + MajI( T2, T3, T4 );
	
	T0 += S1I( T5 ) + ChI( T5, T6, T7 ) + SHA256_K[31] + ( (W15 += s1I( W13 ) + W08 + s0I( W00 ) ) );
	T4 += T0;
	T0 += S0I( T1 ) + MajI( T1, T2, T3 );




	T7 += S1I( T4 ) + ChI( T4, T5, T6 ) + SHA256_K[32] + ( (W00 += s1I( W14 ) + W09 + s0I( W01 ) ) );
	T3 += T7;
	T7 += S0I( T0 ) + MajI( T0, T1, T2 );
	
	T6 += S1I( T3 ) + ChI( T3, T4, T5 ) + SHA256_K[33] + ( (W01 += s1I( W15 ) + W10 + s0I( W02 ) ) );
	T2 += T6;
	T6 += S0I( T7 ) + MajI( T7, T0, T1 );
	
	T5 += S1I( T2 ) + ChI( T2, T3, T4 ) + SHA256_K[34] + ( (W02 += s1I( W00 ) + W11 + s0I( W03 ) ) );
	T1 += T5;
	T5 += S0I( T6 ) + MajI( T6, T7, T0 );
	
	T4 += S1I( T1 ) + ChI( T1, T2, T3 ) + SHA256_K[35] + ( (W03 += s1I( W01 ) + W12 + s0I( W04 ) ) );
	T0 += T4;
	T4 += S0I( T5 ) + MajI( T5, T6, T7 );
	
	T3 += S1I( T0 ) + ChI( T0, T1, T2 ) + SHA256_K[36] + ( (W04 += s1I( W02 ) + W13 + s0I( W05 ) ) );
	T7 += T3;
	T3 += S0I( T4 ) + MajI( T4, T5, T6 );
	
	T2 += S1I( T7 ) + ChI( T7, T0, T1 ) + SHA256_K[37] + ( (W05 += s1I( W03 ) + W14 + s0I( W06 ) ) );
	T6 += T2;
	T2 += S0I( T3 ) + MajI( T3, T4, T5 );
	
	T1 += S1I( T6 ) + ChI( T6, T7, T0 ) + SHA256_K[38] + ( (W06 += s1I( W04 ) + W15 + s0I( W07 ) ) );
	T5 += T1;
	T1 += S0I( T2 ) + MajI( T2, T3, T4 );
	
	T0 += S1I( T5 ) + ChI( T5, T6, T7 ) + SHA256_K[39] + ( (W07 += s1I( W05 ) + W00 + s0I( W08 ) ) );
	T4 += T0;
	T0 += S0I( T1 ) + MajI( T1, T2, T3 );
	
	T7 += S1I( T4 ) + ChI( T4, T5, T6 ) + SHA256_K[40] + ( (W08 += s1I( W06 ) + W01 + s0I( W09 ) ) );
	T3 += T7;
	T7 += S0I( T0 ) + MajI( T0, T1, T2 );
	
	T6 += S1I( T3 ) + ChI( T3, T4, T5 ) + SHA256_K[41] + ( (W09 += s1I( W07 ) + W02 + s0I( W10 ) ) );
	T2 += T6;
	T6 += S0I( T7 ) + MajI( T7, T0, T1 );
	
	T5 += S1I( T2 ) + ChI( T2, T3, T4 ) + SHA256_K[42] + ( (W10 += s1I( W08 ) + W03 + s0I( W11 ) ) );
	T1 += T5;
	T5 += S0I( T6 ) + MajI( T6, T7, T0 );
	
	T4 += S1I( T1 ) + ChI( T1, T2, T3 ) + SHA256_K[43] + ( (W11 += s1I( W09 ) + W04 + s0I( W12 ) ) );
	T0 += T4;
	T4 += S0I( T5 ) + MajI( T5, T6, T7 );
	
	T3 += S1I( T0 ) + ChI( T0, T1, T2 ) + SHA256_K[44] + ( (W12 += s1I( W10 ) + W05 + s0I( W13 ) ) );
	T7 += T3;
	T3 += S0I( T4 ) + MajI( T4, T5, T6 );
	
	T2 += S1I( T7 ) + ChI( T7, T0, T1 ) + SHA256_K[45] + ( (W13 += s1I( W11 ) + W06 + s0I( W14 ) ) );
	T6 += T2;
	T2 += S0I( T3 ) + MajI( T3, T4, T5 );
	
	T1 += S1I( T6 ) + ChI( T6, T7, T0 ) + SHA256_K[46] + ( (W14 += s1I( W12 ) + W07 + s0I( W15 ) ) );
	T5 += T1;
	T1 += S0I( T2 ) + MajI( T2, T3, T4 );
	
	T0 += S1I( T5 ) + ChI( T5, T6, T7 ) + SHA256_K[47] + ( (W15 += s1I( W13 ) + W08 + s0I( W00 ) ) );
	T4 += T0;
	T0 += S0I( T1 ) + MajI( T1, T2, T3 );
	
	
	

	T7 += S1I( T4 ) + ChI( T4, T5, T6 ) + SHA256_K[48] + ( (W00 += s1I( W14 ) + W09 + s0I( W01 ) ) );
	T3 += T7;
	T7 += S0I( T0 ) + MajI( T0, T1, T2 );
	
	T6 += S1I( T3 ) + ChI( T3, T4, T5 ) + SHA256_K[49] + ( (W01 += s1I( W15 ) + W10 + s0I( W02 ) ) );
	T2 += T6;
	T6 += S0I( T7 ) + MajI( T7, T0, T1 );
	
	T5 += S1I( T2 ) + ChI( T2, T3, T4 ) + SHA256_K[50] + ( (W02 += s1I( W00 ) + W11 + s0I( W03 ) ) );
	T1 += T5;
	T5 += S0I( T6 ) + MajI( T6, T7, T0 );
	
	T4 += S1I( T1 ) + ChI( T1, T2, T3 ) + SHA256_K[51] + ( (W03 += s1I( W01 ) + W12 + s0I( W04 ) ) );
	T0 += T4;
	T4 += S0I( T5 ) + MajI( T5, T6, T7 );
	
	T3 += S1I( T0 ) + ChI( T0, T1, T2 ) + SHA256_K[52] + ( (W04 += s1I( W02 ) + W13 + s0I( W05 ) ) );
	T7 += T3;
	T3 += S0I( T4 ) + MajI( T4, T5, T6 );
	
	T2 += S1I( T7 ) + ChI( T7, T0, T1 ) + SHA256_K[53] + ( (W05 += s1I( W03 ) + W14 + s0I( W06 ) ) );
	T6 += T2;
	T2 += S0I( T3 ) + MajI( T3, T4, T5 );
	
	T1 += S1I( T6 ) + ChI( T6, T7, T0 ) + SHA256_K[54] + ( (W06 += s1I( W04 ) + W15 + s0I( W07 ) ) );
	T5 += T1;
	T1 += S0I( T2 ) + MajI( T2, T3, T4 );
	
	T0 += S1I( T5 ) + ChI( T5, T6, T7 ) + SHA256_K[55] + ( (W07 += s1I( W05 ) + W00 + s0I( W08 ) ) );
	T4 += T0;
	T0 += S0I( T1 ) + MajI( T1, T2, T3 );
	
	T7 += S1I( T4 ) + ChI( T4, T5, T6 ) + SHA256_K[56] + ( (W08 += s1I( W06 ) + W01 + s0I( W09 ) ) );
	T3 += T7;
	T7 += S0I( T0 ) + MajI( T0, T1, T2 );
	
	T6 += S1I( T3 ) + ChI( T3, T4, T5 ) + SHA256_K[57] + ( (W09 += s1I( W07 ) + W02 + s0I( W10 ) ) );
	T2 += T6;
	T6 += S0I( T7 ) + MajI( T7, T0, T1 );
	
	T5 += S1I( T2 ) + ChI( T2, T3, T4 ) + SHA256_K[58] + ( (W10 += s1I( W08 ) + W03 + s0I( W11 ) ) );
	T1 += T5;
	T5 += S0I( T6 ) + MajI( T6, T7, T0 );
	
	T4 += S1I( T1 ) + ChI( T1, T2, T3 ) + SHA256_K[59] + ( (W11 += s1I( W09 ) + W04 + s0I( W12 ) ) );
	T0 += T4;
	T4 += S0I( T5 ) + MajI( T5, T6, T7 );
	
	T3 += S1I( T0 ) + ChI( T0, T1, T2 ) + SHA256_K[60] + ( (W12 += s1I( W10 ) + W05 + s0I( W13 ) ) );
	T7 += T3;
	T3 += S0I( T4 ) + MajI( T4, T5, T6 );
	
	T2 += S1I( T7 ) + ChI( T7, T0, T1 ) + SHA256_K[61] + ( (W13 += s1I( W11 ) + W06 + s0I( W14 ) ) );
	T6 += T2;
	T2 += S0I( T3 ) + MajI( T3, T4, T5 );
	
	T1 += S1I( T6 ) + ChI( T6, T7, T0 ) + SHA256_K[62] + ( (W14 += s1I( W12 ) + W07 + s0I( W15 ) ) );
	T5 += T1;
	T1 += S0I( T2 ) + MajI( T2, T3, T4 );
	
	T0 += S1I( T5 ) + ChI( T5, T6, T7 ) + SHA256_K[63] + ( (W15 += s1I( W13 ) + W08 + s0I( W00 ) ) );
	T4 += T0;
	T0 += S0I( T1 ) + MajI( T1, T2, T3 );

	state[0] += T0;
	state[1] += T1;
	state[2] += T2;
	state[3] += T3;
	state[4] += T4;
	state[5] += T5;
	state[6] += T6;
	state[7] += T7;
}

int isLessOrEqual(uint *left, __constant uint *right)
{
	left[7] = bytereverse(left[7]);
	if(left[7] < right[7]) return 1;
	if(left[7] > right[7]) return 0;
	
	left[6] = bytereverse(left[6]);
	if(left[6] < right[6]) return 1;
	if(left[6] > right[6]) return 0;
	
	left[5] = bytereverse(left[5]);
	if(left[5] < right[5]) return 1;
	if(left[5] > right[5]) return 0;
	
	left[4] = bytereverse(left[4]);
	if(left[4] < right[4]) return 1;
	if(left[4] > right[4]) return 0;
	
	left[3] = bytereverse(left[3]);
	if(left[3] < right[3]) return 1;
	if(left[3] > right[3]) return 0;
	
	left[2] = bytereverse(left[2]);
	if(left[2] < right[2]) return 1;
	if(left[2] > right[2]) return 0;
	
	left[1] = bytereverse(left[1]);
	if(left[1] < right[1]) return 1;
	if(left[1] > right[1]) return 0;
	
	left[0] = bytereverse(left[0]);
	if(left[0] < right[0]) return 1;
	if(left[0] > right[0]) return 0;

	return 1;
}

__kernel void search(	__constant uint * block,
						__constant uint * state,
						__constant uint * target,
						__global uint * output,
						const uint base)
{
	uint nonce = base + get_global_id(0);
	__private uint result[8] =
		{0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
	__private uint hash1[16] =
		{state[0], state[1], state[2], state[3], state[4], state[5], state[6], state[7],
		0x80000000, 0, 0, 0, 0, 0, 0, 0x00000100};
	uint data[16] =
		{block[0], block[1], block[2], nonce, block[4], block[5], block[6], block[7],
		block[8], block[9], block[10], block[11], block[12], block[13], block[14], block[15]};

	sha256_process_block(hash1, data);
	sha256_process_block(result, hash1);
	if (((unsigned short*)result)[14] == 0 && isLessOrEqual(result, target)) {
		output[0] = 1;
		output[1] = nonce;
	}
}

// end