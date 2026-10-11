"""Independent P64 full-line target granularity and cached timestamp oracle."""
from pathlib import Path
import ast,hashlib,re,runpy,sys,struct
root=Path(__file__).resolve().parent
runpy.run_path(str(root/'test_p63_fixture.py'))
bridge=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'core/loadtest/CoreBridge.cpp'
baseline=bridge.read_bytes()[:1612838]
assert hashlib.sha256(baseline).hexdigest()=='c142e042108c4e2de18f0a60c0390a593e4a0b82b48de04b13f2d360993c9ead', 'Build78 bridge prefix changed'
assert hashlib.sha256(bridge.read_bytes()[:1657191]).hexdigest()=='684057baf8716eb5560db03cff4317f6b0a699ac11d71c1badbd709741661c55', 'Build79 bridge prefix changed'
assert hashlib.sha256(bridge.read_bytes()[:1704453]).hexdigest()=='f77bbcafd54609c2ba35763257cbe3eacb7d01c936770d8b25badc511b018f4c', 'Build80 bridge prefix changed'
assert hashlib.sha256(bridge.read_bytes()[:1757203]).hexdigest()=='e95c88c8a0aaa86762042a84ccb0a99c1be624940db6edeb2800daaab0aed8ab', 'Build81 bridge prefix changed'
assert hashlib.sha256(bridge.read_bytes()[:1813469]).hexdigest()=='65072fde8fba57cc220d55c846aa7faff85947efa3b949bfbb33258b4be704e2', 'Build82 bridge prefix changed'
assert hashlib.sha256(bridge.read_bytes()[:1874705]).hexdigest()=='85f7ddca129f07fb3cbfd809278c59c6aaa09d786c31f52bd2bc2a65fc1df8fa', 'Build83 bridge prefix changed'
source=bridge.read_text();start=source.index('int armsx3_core_test_reservation_line_targets()')
opening=source.index('{',start);end=opening+1;depth=1
while depth:
    depth+=(source[end]=='{')-(source[end]=='}');end+=1
stage=source[start:end]
code=stage.split('const std::array<u32, 198> opcodes{',1)[1].split('};',1)[0]
def dform(op,rt,ra,imm):return(op<<26)|(rt<<21)|(ra<<16)|(imm&0xffff)
ops=[]
for match in re.finditer(r'\b(LI|LIS|MTCTR|ADDI|BC|STW|LWZ|ORI|MFLR|MTLR|STDU|STD|LD|B|BLR|NOP|LFD|STFD|LVX|STVX|CMPDI|MFSPR|loadReserved|storeConditional|loadWideReserved|storeWideConditional|readCR)\(([^()]*)\)|\b(addPreviousTLS|addDouble|xorVector|addCarryRecord|readConditions)\b',code):
    name,args=match.group(1),match.group(2)
    if name is None:
        ops.append({'addPreviousTLS':(31<<26)|(3<<21)|(3<<16)|(8<<11)|(266<<1),
            'addDouble':(63<<26)|(3<<21)|(1<<16)|(2<<11)|(21<<1)|1,
            'xorVector':(4<<26)|(3<<21)|(1<<16)|(2<<11)|0x4c4,
            'addCarryRecord':(13<<26)|(15<<21)|(14<<16)|1,
            'readConditions':(31<<26)|(16<<21)|(19<<1)}[match.group(3)]);continue
    a=[ast.literal_eval(x.strip().replace('false','False').replace('true','True')) for x in args.split(',')] if args else []
    if name in ['loadReserved','loadWideReserved']:word=(31<<26)|(a[0]<<21)|(a[1]<<11)|((84 if name=='loadWideReserved' else 20)<<1)
    elif name in ['storeConditional','storeWideConditional']:word=(31<<26)|(a[0]<<21)|(a[1]<<11)|((214 if name=='storeWideConditional' else 150)<<1)|1
    elif name=='readCR':word=(31<<26)|(a[0]<<21)|(19<<1)
    elif name=='CMPDI':word=(11<<26)|(a[0]<<23)|(1<<21)|(a[1]<<16)|(a[2]&0xffff)
    elif name=='MFSPR':word=(31<<26)|(a[0]<<21)|(a[1]<<11)|(339<<1)
    elif name in ['LI','LIS']:word=dform(14 if name=='LI' else 15,a[0],0,a[1])
    elif name in ['MTCTR','MFLR','MTLR']:
        word=(31<<26)|(a[0]<<21)|((9 if name=='MTCTR' else 8)<<16)|((339 if name=='MFLR' else 467)<<1)
    elif name in ['STD','STDU','LD']:
        word=dform(58 if name=='LD' else 62,a[0],a[1],a[2]&~3)|(name=='STDU')
    elif name in ['LVX','STVX']:
        word=(31<<26)|(a[0]<<21)|(a[1]<<16)|(a[2]<<11)|((103 if name=='LVX' else 231)<<1)
    elif name in ['LFD','STFD']:word=dform(50 if name=='LFD' else 54,*a)
    elif name=='B':
        word=(18<<26)|(a[0]&0x03fffffc)|((a[1] if len(a)>1 else False)<<1)|(a[2] if len(a)>2 else False)
    elif name=='BLR':word=0x4e800020
    elif name=='NOP':word=0x60000000
    else:word=dform({'ADDI':14,'BC':16,'STW':36,'LWZ':32,'ORI':24}[name],*a)
    ops.append(word)
assert 'const u32 addDouble = (63u << 26) | (3u << 21) | (1u << 16) | (2u << 11) | (21u << 1) | 1u;' in stage
assert 'const u32 xorVector = (4u << 26) | (3u << 21) | (1u << 16) | (2u << 11) | 0x4c4u;' in stage
assert 'const u32 addCarryRecord = (13u << 26) | (15u << 21) | (14u << 16) | 1u;' in stage
assert 'const u32 readConditions = (31u << 26) | (16u << 21) | (19u << 1);' in stage
assert 'return (31u << 26) | (rt << 21) | (rb << 11) | (20u << 1);' in stage
assert 'return (31u << 26) | (rs << 21) | (rb << 11) | (150u << 1) | 1u;' in stage
assert 'const auto readCR = [](u32 rt) { return (31u << 26) | (rt << 21) | (19u << 1); };' in stage
assert len(ops)==198
assert ops==[
    0x7c0802a6,0xf821ff81,0xf8010010,0xf8410018,0x48000031,
    0xe8410018,0x90660008,0xe8010010,0x38210080,0x7c0803a6,0x606a0100,0x48000098,
    0x60000000,0x60000000,0x60000000,0x60000000,
    0x7c0802a6,0xf821ff81,0xf8010010,0xf8410018,0x38402468,0x4800003d,
    0x80ed9000,0x810d900c,0x7c634214,0x906d900c,0x90e60000,0x91060004,
    0xe8410018,0xe8010010,0x38210080,0x7c0803a6,0x4e800020,
    0x60000000,0x60000000,0x60000000,0x38600000,0x7c8903a6,0x38630001,0x4200fffc,0xc8260040,0xc8460048,0xfc61102b,0xd8660010,
    0x7c2628ce,0x7c4658ce,0x106114c4,0x7c6661ce,0x4e800020,
    0x35ee0001,0x2faf0000,0x7e000026,0x7e2102a6,0x92060030,0x92260034,
    0x91e60038,0x419e0008,0x3a401111,0x9246003c,
    0x7ea0992d,0x7ec00026,0x92c60070,0x7e809828,0x7ea0992d,0x7ee00026,0x92e60074,0x7ea0992d,0x7f000026,0x93060078,0x7f209828,0x7f40992d,0x7f600026,0x9366007c,
    0x7f809828,0x60000000,0x7ea0992d,0x7fa00026,0x93a62000,
    0x7f809828,0x935f0000,0x7f40992d,0x7fa00026,0x93a62004,
    0x7f809828,0x7f40992d,0x7fa00026,0x93a62008,
    0x3ca00002,0x60a53000,0x7f802828,0x3b9c0001,0x7f80292d,0x7fa00026,0x93a62010,0x41820018,
    0x7f802828,0x3b9c0001,0x7f80292d,0x4082fff4,0x60000000,0x7fa00026,0x93a62014,0x83850000,0x93862018,
    0x60a50080,0x7f802828,0x3b9c0001,0x7f80292d,0x7fa00026,0x93a62020,0x41820030,
    0x7f802828,0x3b9c0001,0x7f80292d,0x7fa00026,0x93a62024,0x4082ffec,0x60000000,0x48000034,
    0x60000000,0x60000000,0x60000000,0x83850000,0x3b9c0001,0x93850000,
    0x60000000,0x60000000,0x60000000,0x60000000,0x60000000,0x60000000,
    0x7fa00026,0x93a62028,0x83850000,0x9386202c,
    0x38a50080,0x7f8028a8,0x3b9c0001,0x7f8029ad,0x7fa00026,0x93a62030,0x41820018,
    0x7f8028a8,0x3b9c0001,0x7f8029ad,0x4082fff4,0x60000000,0x7fa00026,0x93a62034,
    0xeb850000,0xfb862038,0x7f8029ad,0x7fa00026,0x93a62040,
    0x38b33000,0x3bff3040,0x7f8028a8,0x60000000,0x935f0000,0x7f8029ad,0x7fa00026,0x93a62044,
    0x7f8028a8,0x3b9c0001,0x7f8029ad,0x7fa00026,0x93a62048,0xeb850000,0xfb862050,
    0x7f8029ad,0x7fa00026,0x93a62058,
    0x38a51008,0x7f8028a8,0x3b9c0001,0x38a50008,0x7f8029ad,0x7fa00026,0x93a6205c,0xeb850000,0xfb862060,
    0x7f8028a8,0x3b9c0001,0x38a50080,0x7f8029ad,0x7fa00026,0x93a62068,
    0x38a5ff80,0x7f8028a8,0x3b9c0001,0x7f8029ad,0x7fa00026,0x93a6206c,0xeb850000,0xfb862070,
    0x7f8029ad,0x7fa00026,0x93a62078]
encoded=b''.join(word.to_bytes(4,'big') for word in ops)
assert len(encoded)==792
pool=bytearray(0x40000)
for slot in range(3):pool[0x60+slot*0x70:0x69+slot*0x70]=b'iOSProbe\0'
expected_pool=pool[:];data=bytearray([0xa5]*0x10000);data[0x80:0x89]=b'iOSProbe\0'
for transaction in range(3):
    for worker in range(2):
        offset=0x200+transaction*0x100+worker*0x80
        left=1.5+transaction*0.5+worker*2.0;right=2.25+transaction*0.25+worker*4.0
        data[offset+64:offset+80]=struct.pack('>dd',left,right)
        data[offset+80:offset+96]=bytes((0x10+transaction*17+worker*53+byte*3)&255 for byte in range(16))
        data[offset+96:offset+112]=bytes((0xe1-transaction*11-worker*29-byte*5)&255 for byte in range(16))
for transaction in range(3):
    for worker in range(2):
        out=0x1000+transaction*0x100+worker*0x80
        data[out:out+4]=struct.pack('>I',0x11223300+transaction*0x10+worker)
data[0x3000:0x3004]=struct.pack('>I',0x44556600)
data[0x3080:0x3084]=struct.pack('>I',0x44557700)
data[0x3100:0x3108]=struct.pack('>Q',0x55667788fffffffe)
for transaction in range(3):
    for worker in range(2):
        offset=0x4000+transaction*0x100+worker*0x80
        data[offset:offset+8]=struct.pack('>Q',0x66778899aabbcc00+transaction*0x100+worker*0x10)
for transaction in range(3):
    for worker in range(2):
        offset=0x5008+transaction*0x100+worker*0x80
        data[offset:offset+16]=struct.pack('>QQ',0x778899aabbccdd00+transaction*0x100+worker*0x10,
            0x8899aabbccdde000+transaction*0x100+worker*0x10)
expected_data=data[:]
stacks=[bytearray([0xa5]*0x10000) for _ in range(2)];expected_stacks=[stack[:] for stack in stacks]
contexts=[dict(g=[0]*32,ctr=0,pc=0) for _ in range(2)];totals=[0,0];histories=[]
stops=0;instructions=0;stores={};calls=0;returns=0;fp_loads=fp_stores=fp_adds=vec_loads=vec_stores=vec_xors=0
atomic_loads=atomic_stores=atomic_success=atomic_failure=0
wide_loads=wide_stores=wide_success=wide_failure=0
ordered_skips=ordered_retries=ordered_backedges=ordered_exits=0
reservation_times={}
addresses=[16,144,156,152,160,168,172,176,184,188,192,96,104,112,20,32,40,196,200,204,212,224,None,236,240,248,256,264,268,276,284,292,296,300,304,312,316,320,324,332,336,340,348,356,360,364,368,376,400,408,412,416,420,424,428,432,440,None,None,None,None,None,None,None,524,532,536,540,544,548,552,556,564,588,596,600,604,608,616,624,628,632,636,640,648,652,656,660,668,672,676,680,688,692,696,700,704,708,716,720,724,728,732,736,740,748,752,756,760,764,772,776,780,784,792]
def memory(addr):
    if 0x50000<=addr<0x90000:return pool,addr-0x50000
    if 0x30000<=addr<0x50000:
        worker=(addr-0x30000)//0x10000;return stacks[worker],addr-(0x30000+worker*0x10000)
    assert 0x20000<=addr<0x30000;return data,addr-0x20000
for transaction in range(3):
    previous=totals[:];cross_times=[0,0]
    for worker,c in enumerate(contexts):
        count=17+transaction*3+worker*14;g=c['g'];sp=0x37f90+worker*0x10000
        assert not transaction or g[1]==sp # previous transaction really restored its stack
        g[0]=0xfedc0000;g[1]=sp;g[2]=0x13579000;g[3]=0;g[4]=count
        g[5]=80;g[11]=96;g[12]=32;g[6]=0x20200+transaction*0x100+worker*0x80;g[13]=0x57060+worker*0x70
        g[7]=0x76540000;g[8]=0x87650000;g[9]=0x98760000;g[10]=0xa9870000
        g[14]=(7+transaction if worker else (1<<64)-1);g[15]=0xdead0015;g[16]=0xdead0016;g[17]=0xdead0017;g[18]=0x2222
        g[19]=0x21000+transaction*0x100+worker*0x80;g[20]=0xdead0020;g[21]=0xa1b20000+transaction*0x100+worker*0x10
        g[22]=0xdead0022;g[23]=0xdead0023;g[24]=0xdead0024;g[25]=0xdead0025
        g[26]=0xc3d40000+transaction*0x100+worker*0x10;g[27]=0xdead0027
        g[28]=0xdead0028;g[29]=0xdead0029;g[31]=0x21000+transaction*0x100+(1-worker)*0x80
        c.update(reservation=None,won=False,full=False,snapshot=None,rtime=0,cached=0)
        c.update(cr=0x8a6c5e79^(transaction<<8)^(worker<<12),fpscr=0x13579bdf^(transaction<<20)^(worker<<24),
            so=not worker,ov=bool(transaction&1),ca=bool(worker),cnt=0x15+transaction+worker,vrsave=0x5aa50000|(transaction<<8)|worker)
        c.update(pc=0,ctr=0,lr=0x12340000,count=count,transaction_steps=0,f=[7.0]*32,v=[bytes([0x3c]*16) for _ in range(32)])
    for slice in range(115):
        before=[(c['g'][:],c['ctr'],c['lr'],c['pc'],c['f'][:],c['v'][:]) for c in contexts]
        for worker,c in enumerate(contexts):c.update(steps=0,budget=[4,7,3,5,2*c['count']-6,2,1,1,2,1,1,3,2,2,5,3,2,2,1,1,2,3,1,2 if worker else 1,1,2,2,2,1,2,2,2,1,1,1,2,1,1,1,2,1,1,2,2,1,1,1,2,1 if c.get("won") else 6,2,1,1,1,1,1,1,2,1 if worker==transaction%2 else 3,3 if worker==transaction%2 else 1,1 if worker==transaction%2 else 2,1,1,1,1,1 if worker==transaction%2 else 5,2,1,1,1,1,1,1,2,1 if worker!=transaction%2 else 6,2,1,1,1,2,2,1,1,1,1,2,1,1,1,2,1,1,1,2,1,1,1,1,1,2,1,1,1,1,1,1,2,1,1,1,1,2,1,1,1,2][slice])
        while any(c['pc']<792 and c['steps']<c['budget'] for c in contexts):
            for c in (contexts if (1-transaction%2 if slice==71 else transaction%2)==0 else contexts[::-1]):
                if c['pc']==792 or c['steps']==c['budget']:continue
                if slice==58 and c is not contexts[transaction%2] and contexts[transaction%2]['steps']<contexts[transaction%2]['budget']:continue
                assert c['pc'] in range(0,792,4)
                g=c['g'];x=ops[c['pc']//4];old=c['pc'];c['pc']+=4;c['steps']+=1;c['transaction_steps']+=1;instructions+=1
                op=x>>26;rt=(x>>21)&31;ra=(x>>16)&31;imm=(x&0xffff)-0x10000 if x&0x8000 else x&0xffff
                if op==14:g[rt]=(g[ra] if ra else 0)+imm
                elif op==15:g[rt]=(g[ra] if ra else 0)+(imm<<16)
                elif op==13:
                    assert x==0x35ee0001
                    result=g[14]+1;g[15]=result&((1<<64)-1);c['ca']=result>=(1<<64)
                    field=(2 if g[15]==0 else 4)|int(c['so']);c['cr']=(c['cr']&0x0fffffff)|(field<<28)
                elif op==11:
                    assert x==0x2faf0000
                    field=(2 if g[15]==0 else 4)|int(c['so']);c['cr']=(c['cr']&~15)|field
                elif op in (50,54):
                    addr=g[ra]+imm;block,offset=memory(addr)
                    if op==50:c['f'][rt]=struct.unpack('>d',block[offset:offset+8])[0];fp_loads+=1
                    else:
                        block[offset:offset+8]=struct.pack('>d',c['f'][rt]);stores[addr]=stores.get(addr,0)+1;fp_stores+=1
                elif op==63:
                    assert x==0xfc61102b;c['f'][3]=c['f'][1]+c['f'][2];fp_adds+=1
                    c['cr']=(c['cr']&~0x0f000000)|0x04000000;c['fpscr']=(c['fpscr']&~0xf000)|0x4000
                elif op==4:
                    assert x==0x106114c4;c['v'][3]=bytes(a^b for a,b in zip(c['v'][1],c['v'][2]));vec_xors+=1
                elif op==31:
                    if (x&0x7fe) in (20<<1,84<<1):
                        addr=g[(x>>11)&31];block,off=memory(addr);g[rt]=int.from_bytes(block[off:off+(8 if (x&0x7fe)==84<<1 else 4)],'big')
                        c['full']=slice>=79
                        snapshot=bytes(block[(off&~127):(off&~127)+128]) if c['full'] else bytes(block[off:off+8])
                        if (c['cached']&~127)!=(addr&~127):c['rtime']=reservation_times.get(addr&~127,0)
                        c['snapshot']=snapshot;c['reservation']=(addr,snapshot);atomic_loads+=1
                        if (x&0x7fe)==84<<1:wide_loads+=1
                    elif (x&0x7fe) in (150<<1,214<<1):
                        assert x&1;addr=g[(x>>11)&31];block,off=memory(addr);atomic_stores+=1
                        actual=bytes(block[(off&~127):(off&~127)+128]) if c['full'] else bytes(block[off:off+8])
                        reservation=c['reservation']
                        valid_address=reservation and ((reservation[0]&~127)==(addr&~127) if c['full'] else reservation[0]==addr)
                        success=bool(valid_address and reservation[1]==actual and c['rtime']==reservation_times.get(addr&~127,0))
                        if (x&0x7fe)==214<<1:
                            wide_stores+=1;wide_success+=int(success);wide_failure+=int(not success)
                        if success:
                            size=8 if (x&0x7fe)==214<<1 else 4
                            block[off:off+size]=(g[rt]&((1<<(size*8))-1)).to_bytes(size,'big');stores[addr]=stores.get(addr,0)+1;atomic_success+=1
                        else:atomic_failure+=1
                        if success:
                            reservation_times[addr&~127]=reservation_times.get(addr&~127,0)+128
                            c['rtime']+=128;c['cached']=reservation[0]
                        else:c['cached']=0
                        c['reservation']=None;field=(2 if success else 0)|int(c['so']);c['cr']=(c['cr']&~0xf0000000)|(field<<28)
                    elif (x&0x7fe)==(19<<1):g[rt]=c['cr']
                    elif (x&0x7fe) in (103<<1,231<<1):
                        addr=(g[ra]+g[(x>>11)&31])&~15;block,offset=memory(addr)
                        if (x&0x7fe)==103<<1:c['v'][rt]=bytes(block[offset:offset+16]);vec_loads+=1
                        else:
                            block[offset:offset+16]=c['v'][rt];stores[addr]=stores.get(addr,0)+1;vec_stores+=1
                    elif x==0x7e000026:g[16]=c['cr']
                    elif x==0x7e2102a6:g[17]=(int(c['so'])<<31)|(int(c['ov'])<<30)|(int(c['ca'])<<29)|c['cnt']
                    elif x==0x7c8903a6:c['ctr']=g[4]
                    elif x==0x7c0802a6:g[0]=c['lr']
                    elif x==0x7c0803a6:c['lr']=g[0]
                    else:assert x==0x7c634214;g[3]+=g[8]
                elif op==16:
                    if x==0x4200fffc:
                        c['ctr']-=1
                        if c['ctr']:c['pc']=old+imm
                    elif x==0x41820018:
                        if (c['cr']>>29)&1:c['pc']=old+24
                    elif x==0x41820030:
                        if (c['cr']>>29)&1:c['pc']=old+48;ordered_skips+=1
                        else:ordered_retries+=1
                    elif x==0x4082ffec:
                        if not ((c['cr']>>29)&1):c['pc']=old-20;ordered_backedges+=1
                        else:ordered_exits+=1
                    elif x==0x4082fff4:
                        if not ((c['cr']>>29)&1):c['pc']=old-12
                    else:
                        assert x==0x419e0008
                        if (c['cr']>>1)&1:c['pc']=old+8
                elif op==18:
                    displacement=x&0x03fffffc
                    if displacement&0x02000000:displacement-=0x04000000
                    if x&1:c['lr']=0x10000+old+4;calls+=1
                    c['pc']=old+displacement
                elif op==19:
                    assert x==0x4e800020;c['pc']=(c['lr']&~3)-0x10000;returns+=1
                elif op in (32,36,58,62):
                    addr=g[ra]+((imm&~3) if op in (58,62) else imm);block,offset=memory(addr)
                    size=8 if op in (58,62) else 4
                    if op in (32,58):g[rt]=int.from_bytes(block[offset:offset+size],'big')
                    else:
                        block[offset:offset+size]=g[rt].to_bytes(size,'big');stores[addr]=stores.get(addr,0)+1
                        if op==62 and (x&3)==1:g[ra]=addr
                elif op==24:g[ra]=g[rt]|(x&0xffff)
                else:raise AssertionError(op)
        if slice==46:
            for c in contexts:c['won']=bool(c['cr']&0x20000000)
            assert contexts[0]['won']!=contexts[1]['won']
            assert contexts[transaction%2]['won']
        if slice>=46:expected_data[0x3000:0x3004]=struct.pack('>I',0x44556600+transaction*2+(2 if slice>=48 else 1))
        if slice==94:cross_times=[c['rtime'] for c in contexts]
        if slice==71:
            assert [bool(c['cr']&0x20000000) for c in contexts]==[i!=transaction%2 for i in range(2)]
        if slice>=71:expected_data[0x3100:0x3108]=struct.pack('>Q',0x55667788fffffffe+transaction*2+(2 if slice>=73 else 1))
        if slice==55:
            assert [bool(c['cr']&0x20000000) for c in contexts]==[i==transaction%2 for i in range(2)]
        if slice>=55:expected_data[0x3080:0x3084]=struct.pack('>I',0x44557700+transaction*3+(3 if slice>=63 else 2 if slice>=58 else 1))
        for worker,c in enumerate(contexts):
            g=c['g'];count=c['count'];total=previous[worker]+count;sp=0x37f90+worker*0x10000
            expected_r3=0 if slice<2 else 1 if slice==2 else 3 if slice==3 else count if slice<12 else total
            expected_sp=sp-(128 if slice==0 or slice in [14,15] else 256 if slice<16 else 0)
            expected_lr=0x12340000 if slice==0 or slice>=16 else 0x10058 if slice<14 else 0x10014
            ordered_offsets=[488,500,504,508,512,516,520] if worker==transaction%2 else [452,456,464,444,448,452,456]
            expected_pc=ordered_offsets[slice-57] if 57<=slice<=63 else (228 if worker else 232) if slice==22 else addresses[slice]
            assert c['pc']==expected_pc and c['lr']==expected_lr,(transaction,slice,worker,c['pc'],addresses[slice],c['lr'],expected_lr)
            assert c['ctr']==(count if slice==2 else count-3 if slice==3 else 0)
            assert [g[i] for i in [0,1,2,3,7,8,9,10]]==[
                0x12340000 if slice==0 or slice>=15 else 0x10014,expected_sp,
                0x13579000 if slice==0 or slice>=14 else 0x2468,expected_r3,
                0x76540000 if slice<11 else 0x694f5350,
                0x87650000 if slice<11 else previous[worker],0x98760000,
                0xa9870000 if slice<17 else total|0x100]
            left=1.5+transaction*0.5+worker*2.0;right=2.25+transaction*0.25+worker*4.0;sum_value=left+right
            for reg in range(32):
                expected=left if reg==1 and slice>=5 else right if reg==2 and slice>=5 else sum_value if reg==3 and slice>=6 else 7.0
                assert struct.pack('>d',c['f'][reg])==struct.pack('>d',expected)
            output=g[6]-0x20000;vector_a=bytes(expected_data[output+80:output+96]);vector_b=bytes(expected_data[output+96:output+112])
            vector_result=bytes(a^b for a,b in zip(vector_a,vector_b))
            for reg in range(32):
                expected=vector_a if reg==1 and slice>=8 else vector_b if reg==2 and slice>=8 else vector_result if reg==3 and slice>=9 else bytes([0x3c]*16)
                assert c['v'][reg]==expected
            if slice>=7:expected_data[output+16:output+24]=struct.pack('>d',sum_value)
            if slice>=10:expected_data[output+32:output+48]=vector_result
            assert c['steps']==(c['budget'] if slice<114 else 2)
            if slice<114:stops+=1
            else:assert c['transaction_steps']==2*count+68+(10 if worker else 9)+(12 if c['won'] else 17)+(20 if worker==transaction%2 else 25)+(14 if worker!=transaction%2 else 19)+18+26
            def stackword(addr,value):
                offset=addr-(0x30000+worker*0x10000)
                expected_stacks[worker][offset:offset+8]=value.to_bytes(8,'big')
            stackword(sp-128,sp);stackword(sp-128+16,0x12340000);stackword(sp-128+24,0x13579000)
            if slice>=1:
                stackword(sp-256,sp-128);stackword(sp-256+16,0x10014);stackword(sp-256+24,0x13579000)
            if slice>=12:
                offset=0x6c+worker*0x70;expected_pool[offset:offset+4]=total.to_bytes(4,'big')
            if slice>=13:
                offset=0x200+transaction*0x100+worker*0x80
                expected_data[offset:offset+8]=b'iOSP'+previous[worker].to_bytes(4,'big')
            if slice>=15:expected_data[offset+8:offset+12]=total.to_bytes(4,'big')
            for index in [4,6,11,12,13,30]+([31] if slice!=79 else []):assert g[index]==before[worker][0][index]
        for worker,c in enumerate(contexts):
            condition=4 if worker else 3
            cr=0x8a6c5e79^(transaction<<8)^(worker<<12)
            if slice>=6:cr=(cr&~0x0f000000)|0x04000000
            if slice>=18:cr=(cr&~0xf0000000)|(condition<<28)
            if slice>=19:cr=(cr&~15)|condition
            xer=(0 if worker else 0x80000000)|((transaction&1)<<30)|((int(not worker) if slice>=18 else worker)<<29)|(0x15+transaction+worker)
            fpscr=0x13579bdf^(transaction<<20)^(worker<<24)
            if slice>=6:fpscr=(fpscr&~0xf000)|0x4000
            actual_xer=(int(c['so'])<<31)|(int(c['ov'])<<30)|(int(c['ca'])<<29)|c['cnt']
            assert actual_xer==xer
            readback_cr=cr
            if slice>=24:
                success=(worker==transaction%2 or slice>=63) if slice>=55 else c["won"] if 46<=slice<48 else slice in [26,27] or 30<=slice<38 or slice>=41
                success=False if slice>=77 else (worker!=transaction%2) if 71<=slice<73 else True if slice>=73 else success
                success=((97<=slice<104) or (109<=slice<113)) if slice>=93 else (87<=slice<91) if slice>=79 else success
                field=(2 if success else 0)|int(not worker)
                cr=(cr&~0xf0000000)|(field<<28)
            active=slice in [32,33,36,37,40,44,45,53,54] or (worker!=transaction%2 and slice in [57,61,62]) or slice in [69,70,80,81,82,85,86,94,95,96,101,102,103,107,108]
            assert (c['reservation'] is not None)==active
            if active:assert c['reservation'][0]==(0x25000+transaction*0x100+worker*0x80+(8 if slice<=96 else 16) if slice>=94 else 0x24000+transaction*0x100+worker*0x80 if slice>=80 else 0x23100 if slice>=69 else 0x23080 if slice>=53 else 0x23000 if slice in [44,45] else c['g'][19])
            assert c['cr']==cr and c['fpscr']==fpscr and c['vrsave']==0x5aa50000|(transaction<<8)|worker
            assert [c['g'][reg] for reg in range(14,19)]==[
                7+transaction if worker else (1<<64)-1,
                (8+transaction if worker else 0) if slice>=18 else 0xdead0015,
                readback_cr if slice>=20 else 0xdead0016,xer if slice>=20 else 0xdead0017,
                0x1111 if slice>=23 and worker else 0x2222]
            out=c['g'][6]-0x20000
            if slice>=21:expected_data[out+48:out+60]=struct.pack('>III',readback_cr,xer,8+transaction if worker else 0)
            if slice>=23:expected_data[out+60:out+64]=struct.pack('>I',0x1111 if worker else 0x2222)
        for worker,c in enumerate(contexts):
            addr=0x21000+transaction*0x100+worker*0x80;initial=0x11223300+transaction*0x10+worker
            first=0xa1b20000+transaction*0x100+worker*0x10;second=0xc3d40000+transaction*0x100+worker*0x10
            base=0x8a6c5e79^(transaction<<8)^(worker<<12);base=(base&~0x0f000000)|0x04000000
            base=(base&~15)|(4 if worker else 3)
            failed=(base&~0xf0000000)|(int(not worker)<<28);successful=failed|0x20000000
            assert c['g'][19:28]==[addr,initial if slice>=26 else 0xdead0020,first,
                failed if slice>=25 else 0xdead0022,successful if slice>=27 else 0xdead0023,
                failed if slice>=29 else 0xdead0024,first if slice>=30 else 0xdead0025,second,
                successful if slice>=31 else 0xdead0027]
            peer=0xc3d40000+transaction*0x100+(1-worker)*0x10
            if slice>=26:
                value=second if slice>=41 else peer if slice>=37 else first if slice>=34 else second if slice>=30 else first
                expected_data[addr-0x20000:addr-0x20000+4]=struct.pack('>I',value)
            race_initial=0x44556600+transaction*2;race_cr=successful if c.get('won') else failed
            ordered_won=worker==transaction%2;ordered_base=0x44557700+transaction*3
            ordered_value=ordered_base+3 if slice>=66 else (ordered_base+2 if slice>=58 else ordered_base+1 if slice>=54 else ordered_base) if ordered_won else ordered_base+3 if slice>=62 else ordered_base+2 if slice>=57 else ordered_base+1 if slice>=54 else ordered_base
            wide_won=worker!=transaction%2;wide_base=0x55667788fffffffe+transaction*2
            wide_value=wide_base+2 if slice>=75 or (slice>=73 and not wide_won) else wide_base+1 if slice>=70 else wide_base
            full_address=0x24000+transaction*0x100+worker*0x80
            full_initial=0x66778899aabbcc00+transaction*0x100+worker*0x10
            cross_address=0x25000+transaction*0x100+worker*0x80
            cross_load=0x778899aabbccdd00+transaction*0x100+worker*0x10
            cross_target=0x8899aabbccdde000+transaction*0x100+worker*0x10
            cross_value=cross_load+(2 if slice>=108 else 1 if slice==107 else 2 if slice>=102 else 1 if slice>=95 else 0)
            assert c['g'][28:30]==[
                cross_value if slice>=94 else full_initial+(1 if slice>=86 else 0) if slice>=80 else wide_value if slice>=69 else ordered_value if slice>=53 else race_initial+2 if slice>=50 or (slice>=48 and not c['won']) else race_initial+1 if slice>=45 else
                race_initial if slice>=44 else peer if slice>=40 else first if slice>=36 else second if slice>=32 else 0xdead0028,
                failed if slice>=114 else successful if slice>=110 else failed if slice>=105 else successful if slice>=98 else failed if slice>=92 else successful if slice>=88 else failed if slice>=84 else failed if slice>=78 else successful if slice>=74 else (successful if wide_won else failed) if slice>=72 else (successful if ordered_won or slice>=64 else failed) if slice>=56 else successful if slice>=49 else race_cr if slice>=47 else successful if slice>=42 else failed if slice>=39 else successful if slice>=35 else 0xdead0029]
            assert c['g'][5]==(cross_address+(0x90 if 103<=slice<106 else 16 if slice>=96 else 8) if slice>=93 else full_address if slice>=79 else 0x23100 if slice>=68 else 0x23080 if slice>=52 else 0x23000 if slice>=43 else 80)
            for step,when in enumerate([47,49,51]):
                if slice>=when:
                    output=c['g'][6]-0x20000+0x2010+step*4
                    value=race_cr if step==0 else successful if step==1 else race_initial+2
                    expected_data[output:output+4]=struct.pack('>I',value)
            def ordered_output(displacement,value):
                offset=c['g'][6]-0x20000+displacement
                expected_data[offset:offset+4]=struct.pack('>I',value)
            if slice>=56:ordered_output(0x2020,successful if ordered_won else failed)
            if not ordered_won and slice>=59:ordered_output(0x2024,successful if slice>=64 else failed)
            if slice>=65:ordered_output(0x2028,successful)
            if slice>=67:ordered_output(0x202c,ordered_base+3)
            if slice>=72:ordered_output(0x2030,successful if wide_won else failed)
            if slice>=74:ordered_output(0x2034,successful)
            if slice>=76:
                offset=c['g'][6]-0x20000+0x2038
                expected_data[offset:offset+8]=struct.pack('>Q',wide_base+2)
            if slice>=78:ordered_output(0x2040,failed)
            if slice>=82:
                offset=full_address-0x20000+64
                expected_data[offset:offset+4]=struct.pack('>I',0xc3d40000+transaction*0x100+(1-worker)*0x10)
            if slice>=87:
                offset=full_address-0x20000
                expected_data[offset:offset+8]=struct.pack('>Q',full_initial+1)
            if 80<=slice<94:
                captured=bytearray([0xa5]*128);captured[:8]=struct.pack('>Q',full_initial)
                if slice>=85:captured[64:68]=struct.pack('>I',0xc3d40000+transaction*0x100+(1-worker)*0x10)
                assert c['full'] and c['snapshot']==captured
            if slice>=84:ordered_output(0x2044,failed)
            if slice>=88:ordered_output(0x2048,successful)
            if slice>=90:
                offset=c['g'][6]-0x20000+0x2050
                expected_data[offset:offset+8]=struct.pack('>Q',full_initial+1)
            if slice>=92:ordered_output(0x2058,failed)
            if slice>=97:
                offset=cross_address-0x20000+16
                expected_data[offset:offset+8]=struct.pack('>Q',cross_load+(2 if slice>=109 else 1))
            if slice>=94:
                expected_time=cross_times[worker]+(256 if slice>=109 else 128 if slice>=97 else 0)
                expected_cached=0 if slice>=113 else cross_address+16 if slice>=109 else 0 if slice>=104 else cross_address+8 if slice>=97 else 0
                assert c['rtime']==expected_time and c['cached']==expected_cached
                captured=bytearray([0xa5]*128);captured[8:24]=struct.pack('>QQ',cross_load,cross_load+1 if slice>=101 else cross_target)
                assert c['full'] and c['snapshot']==captured
            if slice>=98:ordered_output(0x205c,successful)
            if slice>=100:
                offset=c['g'][6]-0x20000+0x2060
                expected_data[offset:offset+8]=struct.pack('>Q',cross_load+1)
            if slice>=105:ordered_output(0x2068,failed)
            if slice>=110:ordered_output(0x206c,successful)
            if slice>=112:
                offset=c['g'][6]-0x20000+0x2070
                expected_data[offset:offset+8]=struct.pack('>Q',cross_load+2)
            if slice>=114:ordered_output(0x2078,failed)
            assert c['g'][31]==(0x24040 if slice>=79 else 0x21000)+transaction*0x100+(1-worker)*0x80
            for step,when in enumerate([35,39,42]):
                if slice>=when:
                    output=c['g'][6]-0x20000+0x2000+step*4
                    expected_data[output:output+4]=struct.pack('>I',failed if step==1 else successful)
            out=c['g'][6]-0x20000
            for step,when in enumerate([25,27,29,31]):
                if slice>=when:expected_data[out+112+step*4:out+116+step*4]=struct.pack('>I',successful if step&1 else failed)
        assert pool==expected_pool and data==expected_data and stacks==expected_stacks
    totals=[previous[i]+contexts[i]['count'] for i in range(2)];histories.append(totals[:])
assert histories==[[17,31],[37,65],[60,102]] and stops==684 and instructions==1374 and calls==returns==12
assert stores[0x5006c]==stores[0x500dc]==3
assert sum(count for addr,count in stores.items() if 0x30000<=addr<0x50000)==36
assert sum(count for addr,count in stores.items() if addr<0x21000)==78
assert fp_loads==vec_loads==12 and fp_adds==fp_stores==vec_xors==vec_stores==6
assert atomic_loads==90 and atomic_stores==120 and atomic_success==60 and atomic_failure==60
assert all(count==5 for addr,count in stores.items() if 0x21000<=addr<0x22000)
assert all(count==1 for addr,count in stores.items() if addr<0x21000)
assert stores[0x23000]==6 and data[0x3000:0x3004]==struct.pack('>I',0x44556606)
assert ordered_skips==ordered_retries==ordered_backedges==ordered_exits==3
for transaction in range(3):
    for worker in range(2):
        proof=0x20200+transaction*0x100+worker*0x80+0x2024
        assert stores.get(proof,0)==(0 if worker==transaction%2 else 2)
assert stores[0x23080]==9 and data[0x3080:0x3084]==struct.pack('>I',0x44557709)
assert wide_loads==39 and wide_stores==57 and wide_success==24 and wide_failure==33
assert stores[0x23100]==6 and data[0x3100:0x3108]==struct.pack('>Q',0x5566778900000004)
assert all(stores[0x24000+t*0x100+i*0x80]==1 and stores[0x24040+t*0x100+i*0x80]==1 for t in range(3) for i in range(2))
assert all(stores[0x25010+t*0x100+i*0x80]==2 and not stores.get(0x25008+t*0x100+i*0x80,0) for t in range(3) for i in range(2))
assert all(c['g'][1]==0x37f90+i*0x10000 and c['g'][2]==0x13579000 and c['lr']==0x12340000 for i,c in enumerate(contexts))
for invariant in ['status() == job.status', 'context.cr.pack()', 'context.fpscr.bits.pack()',
    'context.vrsave', 'job.continuation = snapshot(); job.status = status();',
    'slice < 115', 'transaction * 115 + slice', 'slice < 114 ? -2 : 2',
    'program.slices != 345', 'job.status != expectedStatus', 'job.continuation.begin() + 14',
    'if (slice >= 21)', 'if (slice >= 23)', 'context.raddr == job.reservationAddress', 'job.reservationClean', 'context.rtime == job.reservationTime', 'context.res_cached == job.reservationCached', 'context.use_full_rdata == job.fullReservation', 'context.rdata, job.reservationData.data()', 'if (!job.slice)', 'vm::get_super_ptr(pool)']:
    assert invariant in stage,invariant
for invariant in ['ppu_128_reservations_loop_max_length.set(-1)', 'ppu_128_reservations_loop_max_length.set(reservations)',
    'rsx_accurate_res_access.set(false)', 'rsx_accurate_res_access.set(rsxReservations)', 'job.reservationData != captured']:
    assert invariant in stage,invariant
assert stage.count('std::make_unique<named_thread<ppu_thread>>')==2
assert stage.count('peerTLS = armsx3_ios_ppu_probe_alloc_peer_tls(owner, pool);')==1
assert stage.index('struct Callback {')<stage.index('struct StopOwner {')
assert stage.index('(*peer)(); joined = true;')<stage.index('peerTLS = 0; program.tlsMemory = true;')
assert stage.index('segmentCleanup.release();')<stage.index('vm::dealloc(address, vm::main)')<stage.index('vm::close(); initialized = false;')
print('PASS: P64 SHA1='+hashlib.sha1(encoded).hexdigest()+', 198words/792bytes,690slices/684stops/1374instructions,90 reserved loads/120 conditional stores with60 successes/60 failures, old cases plus six cross-word full-line successes/cached timestamp reloads/outside rejections/fresh recoveries/consumed rejections, exact CR readbacks and big-endian words/neighbors/full memory/TLS/stacks; P43-P63 preserved')
