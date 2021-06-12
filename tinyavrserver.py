    # This file is part of tinyavrprogrammer.

    # tinyavrprogrammer is free software: you can redistribute it and/or modify
    # it under the terms of the GNU General Public License as published by
    # the Free Software Foundation, version 3.

    # tinyavrprogrammer is distributed in the hope that it will be useful,
    # but WITHOUT ANY WARRANTY; without even the implied warranty of
    # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    # GNU General Public License for more details.

    # You should have received a copy of the GNU General Public License
    # along with tinyavrprogrammer.  If not, see <https://www.gnu.org/licenses/>.

#Firmware for the tinyavrprogrammer, an RP2040-based high voltage serial programmer (HVSP).
#NOTE: Comments refer to the chip/microcontroller being programmed as "the microcontroller" and to the tinyavrprogrammer as "the programmer"
#NOTE: See the manpage for supported microcontrollers. The support can be trivially extended.

import os
import sys
import usb.core
import usb.util
from ctypes import *
import base64
from enum import *
from time import *

packet_len = 64
class Responses(IntEnum):
    RESERVED = 0, # in effect, the first byte of the return message will only be zero if something goes wrong
    OK = 1,
    # cmd errors
    INVALID_COMMAND=2
    INVALID_ARGUMENT=3
    INVALID_RANGE=4 # out of range, etc
    # hardware errors
    FAILURE=5
    CHIPFAULT=6
    # logic errors
    NOTREADY=7
    NOTPOWERED=8
    NOTCHECKED=9
    NOTERASED=10
class Commands(IntEnum):
    ECHO = 0

    PROG_READY=1
    CHIP_POWERED=2

    POWER_ON=3
    POWER_OFF=4

    CHECK=5
    
    CHIP_ERASE=6

    READ_DATA=7
    WRITE_DATA=8
    READ_HASH_DATA=9

    READ_FLASH=10
    WRITE_FLASH=11

    READ_EEPROM=12
    WRITE_EEPROM=13

    READ_FUSES=14
    WRITE_FUSES=15

    WRITE_LOCK=16

    READ_CALIBRATION=17

    WAS_ERASED=18
def encnum(num:int, b:int):
    return num.to_bytes(b, "little")

#creates a 64 bit hash by xoring the data together 64 bits at a time, exactly the same way the programmer generates its hashes. 
def hash(data:bytes):
    h = 0
    i = 0
    while i < len(data):
        num = int.from_bytes(data[i:(i+8)], "little")
        h = h ^ num
        i += 8
    return h
#some chips only have one fuse register, this will be written into low
class fuses:
    def __init__(self):
        self.low = 0
        self.high = 0
        self.extended = 0
class chipinfo:

    name=""
    def __init__(self, data:bytes):
        data = bytes(data)
        self.lock = data[0]
        data = data[1:] # because I can't be asked to fix every single index
        self.fuseex = data[0]
        self.fusehigh = data[1]
        self.fuselow = data[2]

        self.signature = [i for i in data[3:6]]
        self.calibration = data[6]

        self.cid = data[7]
        self.signature_redundant = [i for i in data[8:12]]
        self.word_bytes = data[12]

        self.flash_bytes = int.from_bytes(data[13:15], "little")
        self.flash_words = int.from_bytes(data[15:17], "little")

        self.flash_page_bytes = data[17]
        self.flash_page_words = data[18]
        self.flash_page_num = data[19]

        self.eeprom_bytes = int.from_bytes(data[20:22], "little")
        self.eeprom_page_bytes = data[22]
        self.eeprom_page_num = data[23]

        rname = data[24:(24+16)]
        for it in rname:
            if(it == 0):
                break
            self.name += chr(it)
class prog:
    dev = None
    cfg = None
    epin = None
    epout = None

    info:chipinfo = None
    #create a package to be sent though the usb interface
    def makepackage(self, cmd:Commands, contents = None):
        if(type(contents) is str):
            contents = contents.encode()
        if contents is None:
            contents = b""
        msg = int(cmd).to_bytes(1, "little") + contents
        msg += b"\0" * (packet_len-len(msg))
        return msg
    # check for errors in the return message
    def checkreturn(self, ret:bytes):
        if(type(ret[0]) is not int):
            assert ord(ret[0]) == int(Responses.OK), "error: " + str(ord(ret[0]))
        else:
            assert ret[0] == int(Responses.OK), "error: " + str(ret[0])
    # write to the programmer
    def write(self, data: bytes):
        if(type(data) is str):
            data = data.encode()
        data += b"\0" * (packet_len-len(data))
        assert len(data) == packet_len
        assert self.epout.write(data, packet_len) == len(data)
    #read from the programmer
    def read(self, tmout=5000):
        b = 1
        dt = []
        dt = self.epin.read(packet_len, timeout=tmout)
        return b"".join([ch.to_bytes(1, "little") for ch in dt])
    def writeread(self, data:bytes, tmout=5000):
        self.write(data)
        return self.read(tmout)

    # should return the exact contents of msg if all goes well.
    def cmd_echo(self, msg:str):
        assert len(msg) <= packet_len-2
        bmsg = msg.encode()
        msg = self.makepackage(Commands.ECHO, bytes([len(bmsg)]) + bmsg)
        ret = self.writeread(msg, 1000)
        self.checkreturn(ret)
        return ret[2:(2+ret[1])].decode(encoding="utf-8")

    # check whether the programmer is ready (main power, 12v stable, etc)
    def cmd_prog_ready(self):
        msg = self.makepackage(Commands.PROG_READY)
        ret = self.writeread(msg)
        self.checkreturn(ret)
        return bool(ret[2])
    def cmd_chip_powered(self):
        msg = self.makepackage(Commands.CHIP_POWERED)
        ret = self.writeread(msg)
        self.checkreturn(ret)
        return bool(ret[2])

    # Power the microcontroller on. Note that you should aim to keep the microcontroller powered for as short a time as possible
    def cmd_power_on(self):
        msg = self.makepackage(Commands.POWER_ON)
        ret = self.writeread(msg)
        self.checkreturn(ret)
    # note that the programmer will power the microcontroller down by itself after a while
    def cmd_power_off(self):
        msg = self.makepackage(Commands.POWER_OFF)
        ret = self.writeread(msg)
        self.checkreturn(ret)

    # Retrieves information about the microcontroller being programmed. Fails if it does not respond. Required before any other operation on the
    def cmd_check(self):
        msg = self.makepackage(Commands.CHECK)
        ret = self.writeread(msg)
        self.checkreturn(ret)
        self.info = chipinfo(ret[2:])
        return self.info
    #erases flash and (not necessarily, check the documentation) the eeprom required before programming the chi
    def cmd_chip_erase(self):
        msg = self.makepackage(Commands.CHIP_ERASE)
        ret = self.writeread(msg)
        self.checkreturn(ret)
    # write data into the programmer's memory
    def cmd_write_data(self, addr:int, data:bytes, dtlen:int = -1):
        if(dtlen == -1):
            dtlen = len(data)
        assert dtlen <= packet_len-4, "write_data is limited to packet_len-4 bytes"
        assert dtlen <= len(data), "dtlen musn't exceed len(data)"
        msg = self.makepackage(Commands.WRITE_DATA, encnum(addr, 2) + encnum(dtlen, 1) + data[0:dtlen])
        ret = self.writeread(msg)
        self.checkreturn(ret)
    # read data from the programmer's memory
    def cmd_read_data(self, addr:int, dtlen:int):
        assert dtlen <= packet_len-2, "write_data is limited to packet_len-2 bytes"
        msg = self.makepackage(Commands.READ_DATA, encnum(addr, 2) + encnum(dtlen, 1))
        ret = self.writeread(msg)
        self.checkreturn(ret)
        return bytes(ret[2:(2+ret[1])])
    def cmd_hash_data(self, addr:int, dtlen:int):
        msg = self.makepackage(Commands.READ_HASH_DATA, encnum(addr, 2) + encnum(dtlen, 2))
        ret = self.writeread(msg)
        self.checkreturn(ret)
        return int.from_bytes(bytes(ret[2:10]), "little")
    
    #do note that this operates on the microcontroller and programmer's memory. To retrieve or write data from the host PC you have to use cmd_read_data and cmd_write_data, which operate on the programmer's internal memory
    def cmd_read_flash(self, startpage:int, npages:int, destination:int):
        msg = self.makepackage(Commands.READ_FLASH, encnum(startpage, 2) + encnum(npages, 2) + encnum(destination, 2))
        ret = self.writeread(msg)
        self.checkreturn(ret)
    #do note that this operates on the microcontroller and programmer's memory. To retrieve or write data from the host PC you have to use cmd_read_data and cmd_write_data, which operate on the programmer's internal memory
    def cmd_write_flash(self, startpage:int, npages:int, source:int):
        msg = self.makepackage(Commands.WRITE_FLASH, encnum(startpage, 2) + encnum(npages, 2) + encnum(source, 2))
        ret = self.writeread(msg)
        self.checkreturn(ret)

    #do note that this operates on the microcontroller and programmer's memory. To retrieve or write data from the host PC you have to use cmd_read_data and cmd_write_data, which operate on the programmer's internal memory
    def cmd_read_eeprom(self, startpage:int, npages:int, destination:int):
        msg = self.makepackage(Commands.READ_EEPROM, encnum(startpage, 2) + encnum(npages, 2) + encnum(destination, 2))
        ret = self.writeread(msg)
        self.checkreturn(ret)
    #do note that this operates on the microcontroller and programmer's memory. To retrieve or write data from the host PC you have to use cmd_read_data and cmd_write_data, which operate on the programmer's internal memory
    def cmd_write_eeprom(self, startpage:int, npages:int, source:int):
        msg = self.makepackage(Commands.WRITE_EEPROM, encnum(startpage, 2) + encnum(npages, 2) + encnum(source, 2))
        ret = self.writeread(msg)
        self.checkreturn(ret)

    # this should return all 0s for fuses that are not present in a given microcontroller
    def cmd_read_fuses(self):
        msg = self.makepackage(Commands.READ_FUSES)
        ret = self.writeread(msg)
        self.checkreturn(ret)
        fs = fuses()
        fs.low = ret[2]
        fs.high = ret[3]
        fs.extended = ret[4]
        return fs

    def cmd_write_fuses(self, loworfuses, high=0, extended=0):
        low = 0
        if(type(loworfuses) == fuses):
            low = loworfuses.low
            high = loworfuses.high
            extended = loworfuses.extended
        else:
            low = loworfuses
        
        msg = self.makepackage(Commands.WRITE_FUSES, encnum(low, 1) + encnum(high, 1) + encnum(extended, 1))
        ret = self.writeread(msg)
        self.checkreturn(ret)        

    def cmd_write_lock(self, lock:int):
        msg = self.makepackage(Commands.WRITE_LOCK, encnum(lock, 1))
        ret = self.writeread(msg)
        self.checkreturn(ret)

    def cmd_read_calibration(self):
        msg = self.makepackage(Commands.READ_CALIBRATION)
        ret = self.writeread(msg)
        self.checkreturn(ret)
        return int.from_bytes(bytes(ret[2:3]), "little")
    
    def cmd_was_erased(self):
        msg = self.makepackage(Commands.WAS_ERASED)
        ret = self.writeread(msg)
        self.checkreturn(ret)
        return int.from_bytes(bytes(ret[2:3]), "little")

    def __init__(self, test=True):
        print("initializing device")
        dev = usb.core.find(idVendor=0xfeed, idProduct=0xf00d)
        if dev is None:
            raise ValueError('Device not found')
        dev.set_configuration()
        self.dev = dev
        cfg = dev.get_active_configuration()
        intf = cfg[(0,0)]
        ep = usb.util.find_descriptor(
        intf,
        # match the first OUT endpoint
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_OUT)

        assert ep is not None, "epout is none"
        self.epout = ep
        ep = usb.util.find_descriptor(
        intf,
        # match the first IN endpoint
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_IN)

        assert ep is not None, "epin is none"
        self.epin = ep
        if(test):
            try:
                testmsg = "testing"
                retmsg = self.cmd_echo(testmsg)
            except AssertionError as ex:
                usb.util.dispose_resources(self.dev)    
                raise ex
            except Exception as ex:
                usb.util.dispose_resources(self.dev)   
                raise ex

            assert retmsg == testmsg, (retmsg + "!=" + testmsg)
        print("success")
    def release(self): # I think __del__ should've been used here instead.
        try: # cleaning the input buffer working around a weird bug
            print("rem:", self.epin.read(packet_len, timeout=100))
        except:
            pass
        self.dev.reset()
        usb.util.dispose_resources(self.dev)

def quicktest(extradelay=1):
    r = None
    g = None
    try:
        g = p
    except:
        p = prog()
        g = p
    p = g
    try:
        p.cmd_power_on()
    except (AssertionError, Exception) as ex:
        print("error starting up the programmer")
        p.cmd_power_off()
        p.release()
        raise ex
    sleep(extradelay)
    try:
        r = p.cmd_check()
        print("OK")
    except AssertionError as ex:
        print("ERR")
        raise ex
    p.cmd_power_off()
    p.release()
    return r
def startprog():
    p = prog()
    try:
        p.cmd_power_on()
        p.cmd_check()
    except:
        print("CHECK FAILED")
        p.cmd_power_off()
        p.release()
        assert False, "prog check failed"
    return p

def testread():
    p = prog()
    p.cmd_power_on()
    try:
        p.cmd_check()
    except:
        print("CHECK FAILED")
        p.cmd_power_off()
        p.release()
    p.cmd_read_flash(0, 1, 0)
    ret = p.cmd_read_data(0, 60)
    p.cmd_power_off()
    p.release()
    print("data received:")
    print(ret)
    return ret
def testpages(initial=0, toread=4):
    p = startprog()
    try:
        p.cmd_power_on()
        p.cmd_read_flash(initial, toread, 0)

        n = p.info.flash_page_bytes*toread
        addr = 0
        data = b""
        while n > 0:
            tr = min(n, packet_len-4)
            data += p.cmd_read_data(addr, tr)
            addr += tr
            n -= tr

        pages = []
        identities = []
        idc = 0
        for i in range(0, toread):
            pg = (data[(i*p.info.flash_page_bytes) : (((i+1)*p.info.flash_page_bytes))])

            ii = 0
            b = False
            while ii < len(pages):
                if(pages[ii] == pg):
                    identities.append(identities[ii])
                    b = True
                    break
                ii += 1
            if not b:
                identities.append(idc)
                idc += 1

            pages.append(pg)
            print("PAGE:", initial+i, "\n")
            print(pg)
            print("\n")

        print("identities:", identities)
        p.cmd_power_off()
        p.release()
        return (pages, identities)
    except AssertionError as ex:
        p.cmd_power_off()
        p.release()
        raise ex
    except Exception as ex:
        p.cmd_power_off()
        p.release()
        raise ex
    except:
        p.cmd_power_off()
        p.release()
        assert False, "ffs"
def testpagesnr(initial, toread):
    testpages(initial, toread)

def parse_hex_file(filename):
    data = []
    with open(filename) as file:
        for line in file:
            assert line[0] == ":"
            leng = int(line[1:3], 16)
            addr = int(line[3:7], 16)
            cmd = int(line[7:9], 16)
            dt = []
            if(leng > 0):
                i = 0
                while(i < leng*2):
                    dt.append(int(line[(9+i):(9+i+2)], 16))
                    i+=2
            if(cmd == 1):
                break
            assert cmd == 0, "command not supported: " + str(cmd)

            if(addr+leng > len(data)):
                data += [0] * (addr+leng-len(data))
            for i in range(0, leng):
                data[i+addr] = dt[i]
    return bytes(data)
def parse_data_file(filename, form):
    if(form == "a"):
        if(".hex" in filename or ".eep" in filename):
            form = "i"
        else:
            assert False, "unable to identify format"
    if(form == "i"):
        return parse_hex_file(filename)
    elif form == "r":
        with open(filename, "rb") as file:
            return file.read()
    elif form == "m":
        dt = []
        l0 = filename.split(",")
        l1 = filename.split(" ")
        if(len(l0) > len(l1)):
            dt = l0
        else:
            dt = l1
        dt = [int(it, 16) for it in dt]
        return bytes(dt)
    else:
        assert False, "unsupported format - " + form 
def dump_flash(initial=0, toread=0):
    p = startprog()
    try:
        p.cmd_power_on()
        if(toread == 0):
            toread = p.info.flash_page_num
        p.cmd_read_flash(initial, toread, 0)

        n = p.info.flash_page_bytes*toread
        addr = 0
        data = b""
        while n > 0:
            tr = min(n, packet_len-4)
            data += p.cmd_read_data(addr, tr)
            addr += tr
            n -= tr
        p.cmd_power_off()
        p.release()
        return data
    except AssertionError as ex:
        p.cmd_power_off()
        p.release()
        raise ex
def dump_eeprom(initial=0, toread=0):
    p = startprog()
    try:
        p.cmd_power_on()
        if(toread == 0):
            toread = p.info.eeprom_page_num
        p.cmd_read_eeprom(initial, toread, 0)

        n = p.info.eeprom_page_bytes*toread
        addr = 0
        data = b""
        while n > 0:
            tr = min(n, packet_len-4)
            data += p.cmd_read_data(addr, tr)
            addr += tr
            n -= tr
        p.cmd_power_off()
        p.release()
        return data
    except AssertionError as ex:
        p.cmd_power_off()
        p.release()
        raise ex

def dump_info():
    p = startprog()
    p.cmd_power_off()
    p.release()
    return p.info

def upload_flash(filename, format="i"):
    print("initializing upload")
    data = parse_data_file(filename, format)
    p = startprog()
    try:
        print("powering on")
        p.cmd_power_on()
        p.cmd_check()
        print("uploading to the buffer")
        data += b"\0" * (len(data) % p.info.flash_page_bytes)
        n = len(data)
        i =0
        while i < n:
            ln = min(packet_len-4, n-i)
            p.cmd_write_data(i, data[i:(i+ln)], ln)
            i += ln
        print("verifying")
        hsh = p.cmd_hash_data(0, n)
        assert hsh == hash(data), "invalid hash on initial write " + str(hsh) + " instead of " + str(hash(data))
        print("hash correct")

        print("writing flash")
        if(not p.cmd_was_erased()):
            p.cmd_chip_erase()
        p.cmd_write_flash(0, int(n / p.info.flash_page_bytes), 0)

        print("reading back")
        p.cmd_read_flash(0, int(n / p.info.flash_page_bytes), 0)

        hsh = p.cmd_hash_data(0, n)

        print("verifiying")
        assert hsh == hash(data), "invalid hash on return read " + str(hsh) + " instead of " + str(hash(data))
        print("hash correct")

        print("powering off")
        p.cmd_power_off()
        p.release()
        print("success!")
    except AssertionError as ex:
        p.cmd_power_off()
        p.release()
        raise ex

def upload_eeprom(filename, format="i"):
    print("initializing upload")
    data = parse_data_file(filename, format)
    p = startprog()
    try:
        print("powering on")
        p.cmd_power_on()
        p.check()
        print("uploading to the buffer")
        data += b"\0" * (len(data) % p.info.eeprom_page_bytes)
        n = len(data)
        i =0
        while i < n:
            ln = min(packet_len-4, n-i)
            p.cmd_write_data(i, data[i:(i+ln)], ln)
            i += ln

        print("verifying")
        assert p.cmd_hash_data(0, n) == hash(data), "invalid hash on initial write"
        print("hash correct")

        print("writing flash")
        if(not p.cmd_was_erased()):
            p.cmd_chip_erase()
        p.cmd_write_eeprom(0, n / p.info.eeprom_page_bytes)

        print("reading back")
        p.cmd_read_eeprom(0, n / p.info.eeprom_page_bytes)

        print("verifiying")
        assert p.cmd_hash_data(0, n) == hash(data), "invalid hash on return read"
        print("hash correct")

        print("powering off")
        p.cmd_power_off()
        p.release()
        print("success!")
    except AssertionError as ex:
        p.cmd_power_off()
        p.release()
        raise ex

def set_lock_bits(lock1orlock, lock2=None):
    lock = 0
    if(lock2 == None):
        lock = lock1orlock
    else:
        lock = lock1orlock | (lock2 << 1)
    p = startprog()
    try:
        p.cmd_power_on()
        p.cmd_write_lock(lock)
        p.cmd_power_off()
        p.release()
    except AssertionError as ex:
        p.cmd_power_off()
        p.release()
        raise ex

def matcharg(s):
    for it in sys.argv[1:]:
        if s in it:
            return True 
    return False

#parse an AVRDUDE command
def execute_cmd(cmd):
    noautoerase = matcharg("-D")
    forceerase = matcharg("-e")
    forced = matcharg("-F")

    print("executing", cmd)

    mt = cmd[0]
    op = cmd[1]
    filename = cmd[2]
    form = cmd[3]

    if op == "r":
        if form != "r" and form != "m":
            print ("unsupported format " + op)
            return 1
        data = b""
        if mt == "flash":
            data = dump_flash()
        elif mt == "eeprom":
            data = dump_eeprom()
        elif mt == "signature":
            data = bytes(dump_info().signature)
        elif mt == "lock":
            data = bytes([dump_info().lock])
        elif mt == "calibration":
            data = bytes([dump_info().calibration])
        elif mt == "hfuse":
            data = bytes([dump_info().fusehigh])
        elif mt == "lfuse":
            data = bytes([dump_info().fuselow])
        elif mt == "efuse":
            data = bytes([dump_info().fuseex])
        else:
            print("invalid read command,", mt, filename, form)
            return 1
        if(form == "m"):
            print ("data:")
            print(data)
        else:
            with open(filename, "wb") as file:
                file.write(data)
    elif op == "w":
        if mt == "flash":
            upload_flash(filename, form)
        elif mt == "eeprom":
            upload_eeprom(filename, form)
        else:
            data = parse_data_file(filename, form)
            if type(data) == int:
                data = bytes([data])
            p = startprog()
            p.cmd_power_on()
            try:
                invalidcommand = False
                if mt == "lock":
                    data = p.cmd_write_lock(data[0])
                elif mt == "calibration":
                    data = p.cmd_write_calibration(data[0])
                elif mt == "hfuse":
                    print("writing", data[0], "into fusehigh. fuselow is", p.info.fuselow)
                    data = p.cmd_write_fuses(p.info.fuselow, data[0], p.info.fuseex)
                elif mt == "lfuse":
                    print("writing", data[0], "into fuselow. fusehigh is", p.info.fusehigh)
                    data = p.cmd_write_fuses(data[0], p.info.fusehigh, p.info.fuseex)
                elif mt == "efuse":
                    data = p.cmd_write_fuses(p.info.fuselow, p.info.fusehigh, data[0])
                else:
                    invalidcommand = True
                p.cmd_power_off()
                p.release()
                if invalidcommand:
                    print("invalid write command,", mt, filename, form)
                    return 1
            except (AssertionError, Exception) as ex:
                p.cmd_power_off()
                p.release()
                raise ex
            except:
                print("internal error", mt, op, filename, form)
                p.cmd_power_off()
                p.release()
                return 1
        return 0
    elif op == "v":
        print("operation not supported", mt, op, filename, form)
        return 1
    else:
        print("invalid operation", op)
        return 1


#this function parses the script arguments in a way that's compatible with AVRDUDE. See the AVRDUDE man page.
def main(targetchip):
    forced = matcharg("-F")
    if not forced:
        b = True
        for i in range(0, 3):
            info = None
            try:
                info = dump_info()
            except (AssertionError, Exception) as ex:
                print("error dumping info")
                print(ex)
                continue
            if not info.name == targetchip[0] and not info.name == targetchip[1]:
                print("invalid microcontroller", info.name)
                break
            b = False
            print ("detected microcontroller:", info.name)
            break
        if b:
            print("Unable to communicate with the microcontroller/programmer")
            return 1
    cmds = []
    i = 1
    while i < len(sys.argv):
        strip = sys.argv[i].replace(" ", "")
        if strip[0] == "-" and strip[1] == "U":
            argv = sys.argv[i]
            if(len(strip) == 2 and i < len(sys.argv)-1 and ":" in sys.argv[i+1]):
                argv = sys.argv[i+1]
                i+= 1
            cmd = argv.split(":")
            if(len(cmd) < 4):
                cmd.append("a")
            cmd[0] = cmd[0].replace("-U ", "")
            cmd[0] = cmd[0].replace("-U", "")
            while cmd[0] == " ":
                cmd = cmd[1:]
            cmds.append(cmd)
        i+=1
    suci = 0
    err = 0
    print("cmds", cmds)
    for it in cmds:
        suci+=1
        err = execute_cmd(it)
        if err != 0:
            break

    print("Done. Attempted to execute", suci, "commands")
    print("retval", err)
    return err



