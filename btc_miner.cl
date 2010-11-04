#ifdef VECTORS
typedef uint2 u;
#else
typedef uint u;
#endif

#ifdef OLD_STREAM
#pragma OPENCL EXTENSION cl_amd_media_ops : enable
#define rot(x, y) amd_bitalign(x, x, (u)(32-y))
#else
#define rot(x, y) rotate(x, (u)y)
#endif

#define R(x) (work[x] = (rot(work[x-2],15)^rot(work[x-2],13)^((work[x-2])>>10)) + work[x-7] + (rot(work[x-15],25)^rot(work[x-15],14)^((work[x-15])>>3)) + work[x-16])
#define sharound(a,b,c,d,e,f,g,h,x,K) {h=(h+(rot(e, 26)^rot(e, 21)^rot(e, 7))+(g^(e&(f^g)))+K+x); t1=(rot(a, 30)^rot(a, 19)^rot(a, 10))+((a&b)|(c&(a|b))); d+=h; h+=t1;}

#ifdef NVIDIA
bool belowOrEquals(const uint x, const uint target)
{
	uchar* b = (uchar *)&x;
	uchar* l = (uchar *)&target;
	if(b[0] < l[3]) return true;
	if(b[0] > l[3]) return false;
	if(b[1] < l[2]) return true;
	if(b[1] > l[2]) return false;
	if(b[2] < l[1]) return true;
	if(b[2] > l[1]) return false;
	if(b[3] < l[0]) return true;
	if(b[3] > l[0]) return false;
	return true;
}
#else
#define bytereverse(x) ( ((x) << 24) | (((x) << 8) & 0x00ff0000) | (((x) >> 8) & 0x0000ff00) | ((x) >> 24) )
bool belowOrEquals(const uint x, const uint target)
{
	return bytereverse(x)<=target;
}
#endif

__kernel void search(	const uint block0, const uint block1, const uint block2,
						const uint state0, const uint state1, const uint state2, const uint state3,
						const uint state4, const uint state5, const uint state6, const uint state7,
						const uint B1, const uint C1, const uint D1,
						const uint F1, const uint G1, const uint H1,
						const uint target,
						const uint base,
						__global uint * output)
{
	u nonce;
#ifdef VECTORS	
	nonce.x = base + get_global_id(0);
	nonce.y = nonce.x + 0x80000000;
#else
	nonce = base + get_global_id(0);
#endif

	u work[64];
    u A,B,C,D,E,F,G,H;
	u t1;
	
	A=state0;
	B=B1;
	C=C1;
	D=D1;
	E=state4;
	F=F1;
	G=G1;
	H=H1;
	
	work[0]=block0;
	work[1]=block1;
	work[2]=block2;
	work[3]=nonce;
	work[4]=0x80000000;
	work[5]=0x00000000;
	work[6]=0x00000000;
	work[7]=0x00000000;
	work[8]=0x00000000;
	work[9]=0x00000000;
	work[10]=0x00000000;
	work[11]=0x00000000;
	work[12]=0x00000000;
	work[13]=0x00000000;
	work[14]=0x00000000;
	work[15]=0x00000280;

	// first 3 rounds already done
	//sharound(A,B,C,D,E,F,G,H,work[0],0x428A2F98);
	//sharound(H,A,B,C,D,E,F,G,work[1],0x71374491);
	//sharound(G,H,A,B,C,D,E,F,work[2],0xB5C0FBCF);
	sharound(F,G,H,A,B,C,D,E,work[3],0xE9B5DBA5);
	sharound(E,F,G,H,A,B,C,D,work[4],0x3956C25B);
	sharound(D,E,F,G,H,A,B,C,work[5],0x59F111F1);
	sharound(C,D,E,F,G,H,A,B,work[6],0x923F82A4);
	sharound(B,C,D,E,F,G,H,A,work[7],0xAB1C5ED5);
	sharound(A,B,C,D,E,F,G,H,work[8],0xD807AA98);
	sharound(H,A,B,C,D,E,F,G,work[9],0x12835B01);
	sharound(G,H,A,B,C,D,E,F,work[10],0x243185BE);
	sharound(F,G,H,A,B,C,D,E,work[11],0x550C7DC3);
	sharound(E,F,G,H,A,B,C,D,work[12],0x72BE5D74);
	sharound(D,E,F,G,H,A,B,C,work[13],0x80DEB1FE);
	sharound(C,D,E,F,G,H,A,B,work[14],0x9BDC06A7);
	sharound(B,C,D,E,F,G,H,A,work[15],0xC19BF174);
	sharound(A,B,C,D,E,F,G,H,R(16),0xE49B69C1);
	sharound(H,A,B,C,D,E,F,G,R(17),0xEFBE4786);
	sharound(G,H,A,B,C,D,E,F,R(18),0x0FC19DC6);
	sharound(F,G,H,A,B,C,D,E,R(19),0x240CA1CC);
	sharound(E,F,G,H,A,B,C,D,R(20),0x2DE92C6F);
	sharound(D,E,F,G,H,A,B,C,R(21),0x4A7484AA);
	sharound(C,D,E,F,G,H,A,B,R(22),0x5CB0A9DC);
	sharound(B,C,D,E,F,G,H,A,R(23),0x76F988DA);
	sharound(A,B,C,D,E,F,G,H,R(24),0x983E5152);
	sharound(H,A,B,C,D,E,F,G,R(25),0xA831C66D);
	sharound(G,H,A,B,C,D,E,F,R(26),0xB00327C8);
	sharound(F,G,H,A,B,C,D,E,R(27),0xBF597FC7);
	sharound(E,F,G,H,A,B,C,D,R(28),0xC6E00BF3);
	sharound(D,E,F,G,H,A,B,C,R(29),0xD5A79147);
	sharound(C,D,E,F,G,H,A,B,R(30),0x06CA6351);
	sharound(B,C,D,E,F,G,H,A,R(31),0x14292967);
	sharound(A,B,C,D,E,F,G,H,R(32),0x27B70A85);
	sharound(H,A,B,C,D,E,F,G,R(33),0x2E1B2138);
	sharound(G,H,A,B,C,D,E,F,R(34),0x4D2C6DFC);
	sharound(F,G,H,A,B,C,D,E,R(35),0x53380D13);
	sharound(E,F,G,H,A,B,C,D,R(36),0x650A7354);
	sharound(D,E,F,G,H,A,B,C,R(37),0x766A0ABB);
	sharound(C,D,E,F,G,H,A,B,R(38),0x81C2C92E);
	sharound(B,C,D,E,F,G,H,A,R(39),0x92722C85);
	sharound(A,B,C,D,E,F,G,H,R(40),0xA2BFE8A1);
	sharound(H,A,B,C,D,E,F,G,R(41),0xA81A664B);
	sharound(G,H,A,B,C,D,E,F,R(42),0xC24B8B70);
	sharound(F,G,H,A,B,C,D,E,R(43),0xC76C51A3);
	sharound(E,F,G,H,A,B,C,D,R(44),0xD192E819);
	sharound(D,E,F,G,H,A,B,C,R(45),0xD6990624);
	sharound(C,D,E,F,G,H,A,B,R(46),0xF40E3585);
	sharound(B,C,D,E,F,G,H,A,R(47),0x106AA070);
	sharound(A,B,C,D,E,F,G,H,R(48),0x19A4C116);
	sharound(H,A,B,C,D,E,F,G,R(49),0x1E376C08);
	sharound(G,H,A,B,C,D,E,F,R(50),0x2748774C);
	sharound(F,G,H,A,B,C,D,E,R(51),0x34B0BCB5);
	sharound(E,F,G,H,A,B,C,D,R(52),0x391C0CB3);
	sharound(D,E,F,G,H,A,B,C,R(53),0x4ED8AA4A);
	sharound(C,D,E,F,G,H,A,B,R(54),0x5B9CCA4F);
	sharound(B,C,D,E,F,G,H,A,R(55),0x682E6FF3);
	sharound(A,B,C,D,E,F,G,H,R(56),0x748F82EE);
	sharound(H,A,B,C,D,E,F,G,R(57),0x78A5636F);
	sharound(G,H,A,B,C,D,E,F,R(58),0x84C87814);
	sharound(F,G,H,A,B,C,D,E,R(59),0x8CC70208);
	sharound(E,F,G,H,A,B,C,D,R(60),0x90BEFFFA);
	sharound(D,E,F,G,H,A,B,C,R(61),0xA4506CEB);
	sharound(C,D,E,F,G,H,A,B,R(62),0xBEF9A3F7);
	sharound(B,C,D,E,F,G,H,A,R(63),0xC67178F2);

	work[0]=state0+A;
	work[1]=state1+B;
	work[2]=state2+C;
	work[3]=state3+D;
	work[4]=state4+E;
	work[5]=state5+F;
	work[6]=state6+G;
	work[7]=state7+H;
	work[8]=0x80000000;
	work[9]=0x00000000;
	work[10]=0x00000000;
	work[11]=0x00000000;
	work[12]=0x00000000;
	work[13]=0x00000000;
	work[14]=0x00000000;
	work[15]=0x00000100;

	A=0x6a09e667;
	B=0xbb67ae85;
	C=0x3c6ef372;
	D=0xa54ff53a;
	E=0x510e527f;
	F=0x9b05688c;
	G=0x1f83d9ab;
	H=0x5be0cd19;

	sharound(A,B,C,D,E,F,G,H,work[0],0x428A2F98);
	sharound(H,A,B,C,D,E,F,G,work[1],0x71374491);
	sharound(G,H,A,B,C,D,E,F,work[2],0xB5C0FBCF);
	sharound(F,G,H,A,B,C,D,E,work[3],0xE9B5DBA5);
	sharound(E,F,G,H,A,B,C,D,work[4],0x3956C25B);
	sharound(D,E,F,G,H,A,B,C,work[5],0x59F111F1);
	sharound(C,D,E,F,G,H,A,B,work[6],0x923F82A4);
	sharound(B,C,D,E,F,G,H,A,work[7],0xAB1C5ED5);
	sharound(A,B,C,D,E,F,G,H,work[8],0xD807AA98);
	sharound(H,A,B,C,D,E,F,G,work[9],0x12835B01);
	sharound(G,H,A,B,C,D,E,F,work[10],0x243185BE);
	sharound(F,G,H,A,B,C,D,E,work[11],0x550C7DC3);
	sharound(E,F,G,H,A,B,C,D,work[12],0x72BE5D74);
	sharound(D,E,F,G,H,A,B,C,work[13],0x80DEB1FE);
	sharound(C,D,E,F,G,H,A,B,work[14],0x9BDC06A7);
	sharound(B,C,D,E,F,G,H,A,work[15],0xC19BF174);
	sharound(A,B,C,D,E,F,G,H,R(16),0xE49B69C1);
	sharound(H,A,B,C,D,E,F,G,R(17),0xEFBE4786);
	sharound(G,H,A,B,C,D,E,F,R(18),0x0FC19DC6);
	sharound(F,G,H,A,B,C,D,E,R(19),0x240CA1CC);
	sharound(E,F,G,H,A,B,C,D,R(20),0x2DE92C6F);
	sharound(D,E,F,G,H,A,B,C,R(21),0x4A7484AA);
	sharound(C,D,E,F,G,H,A,B,R(22),0x5CB0A9DC);
	sharound(B,C,D,E,F,G,H,A,R(23),0x76F988DA);
	sharound(A,B,C,D,E,F,G,H,R(24),0x983E5152);
	sharound(H,A,B,C,D,E,F,G,R(25),0xA831C66D);
	sharound(G,H,A,B,C,D,E,F,R(26),0xB00327C8);
	sharound(F,G,H,A,B,C,D,E,R(27),0xBF597FC7);
	sharound(E,F,G,H,A,B,C,D,R(28),0xC6E00BF3);
	sharound(D,E,F,G,H,A,B,C,R(29),0xD5A79147);
	sharound(C,D,E,F,G,H,A,B,R(30),0x06CA6351);
	sharound(B,C,D,E,F,G,H,A,R(31),0x14292967);
	sharound(A,B,C,D,E,F,G,H,R(32),0x27B70A85);
	sharound(H,A,B,C,D,E,F,G,R(33),0x2E1B2138);
	sharound(G,H,A,B,C,D,E,F,R(34),0x4D2C6DFC);
	sharound(F,G,H,A,B,C,D,E,R(35),0x53380D13);
	sharound(E,F,G,H,A,B,C,D,R(36),0x650A7354);
	sharound(D,E,F,G,H,A,B,C,R(37),0x766A0ABB);
	sharound(C,D,E,F,G,H,A,B,R(38),0x81C2C92E);
	sharound(B,C,D,E,F,G,H,A,R(39),0x92722C85);
	sharound(A,B,C,D,E,F,G,H,R(40),0xA2BFE8A1);
	sharound(H,A,B,C,D,E,F,G,R(41),0xA81A664B);
	sharound(G,H,A,B,C,D,E,F,R(42),0xC24B8B70);
	sharound(F,G,H,A,B,C,D,E,R(43),0xC76C51A3);
	sharound(E,F,G,H,A,B,C,D,R(44),0xD192E819);
	sharound(D,E,F,G,H,A,B,C,R(45),0xD6990624);
	sharound(C,D,E,F,G,H,A,B,R(46),0xF40E3585);
	sharound(B,C,D,E,F,G,H,A,R(47),0x106AA070);
	sharound(A,B,C,D,E,F,G,H,R(48),0x19A4C116);
	sharound(H,A,B,C,D,E,F,G,R(49),0x1E376C08);
	sharound(G,H,A,B,C,D,E,F,R(50),0x2748774C);
	sharound(F,G,H,A,B,C,D,E,R(51),0x34B0BCB5);
	sharound(E,F,G,H,A,B,C,D,R(52),0x391C0CB3);
	sharound(D,E,F,G,H,A,B,C,R(53),0x4ED8AA4A);
	sharound(C,D,E,F,G,H,A,B,R(54),0x5B9CCA4F);
	sharound(B,C,D,E,F,G,H,A,R(55),0x682E6FF3);
	sharound(A,B,C,D,E,F,G,H,R(56),0x748F82EE);
	sharound(H,A,B,C,D,E,F,G,R(57),0x78A5636F);
	sharound(G,H,A,B,C,D,E,F,R(58),0x84C87814);
	sharound(F,G,H,A,B,C,D,E,R(59),0x8CC70208);
	sharound(E,F,G,H,A,B,C,D,R(60),0x90BEFFFA);
	sharound(D,E,F,G,H,A,B,C,R(61),0xA4506CEB);
	//we don't need to do these last 2 rounds as they update F, B, E and A, but we only care about G and H
	//sharound(C,D,E,F,G,H,A,B,R(62),0xBEF9A3F7);
	//sharound(B,C,D,E,F,G,H,A,R(63),0xC67178F2);

	G+=0x1f83d9ab;
	H+=0x5be0cd19;

#ifdef VECTORS
	if((H.x==0) && (belowOrEquals(G.x, target)))
	{
		output[0] = nonce.x;
	}
	if((H.y==0) && (belowOrEquals(G.y, target)))
	{
		output[0] = nonce.y;
	}
#else
	if((H==0) && (belowOrEquals(G, target)))
	{
		output[0] = nonce;
	}
#endif
}

// end