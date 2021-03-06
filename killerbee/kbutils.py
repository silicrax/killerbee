import usb, serial
import os, glob
import time
import random
from struct import pack
from config import *       #to get DEV_ENABLE_* variables

RZ_USB_VEND_ID      = 0x03EB
RZ_USB_PROD_ID      = 0x210A
ZN_USB_VEND_ID      = 0x04D8
ZN_USB_PROD_ID      = 0x000E
#FTDI_USB_VEND_ID      = 0x0403
#FTDI_USB_PROD_ID      = 0x6001
usbVendorList = [RZ_USB_VEND_ID, ZN_USB_VEND_ID]
usbProductList = [RZ_USB_PROD_ID, ZN_USB_PROD_ID]

# Global variables
gps_devstring = None

class KBCapabilities:
    '''
    Class to store and report on the capabilities of a specific KillerBee device.
    '''
    NONE               = 0x00 #: Capabilities Flag: No Capabilities
    SNIFF              = 0x01 #: Capabilities Flag: Can Sniff
    SETCHAN            = 0x02 #: Capabilities Flag: Can Set the Channel
    INJECT             = 0x03 #: Capabilities Flag: Can Inject Frames
    PHYJAM             = 0x04 #: Capabilities Flag: Can Jam PHY Layer
    SELFACK            = 0x05 #: Capabilities Flag: Can ACK Frames Automatically
    PHYJAM_REFLEX      = 0x06 #: Capabilities Flag: Can Jam PHY Layer Reflexively
    def __init__(self):
        self._capabilities = {
                self.NONE : False,
                self.SNIFF : False,
                self.SETCHAN : False,
                self.INJECT : False,
                self.PHYJAM : False,
                self.SELFACK: False,
                self.PHYJAM_REFLEX: False}
    def check(self, capab):
        if capab in self._capabilities:
            return self._capabilities[capab]
        else:
            return False
    def getlist(self):
        return self._capabilities
    def setcapab(self, capab, value):
        self._capabilities[capab] = value
    def require(self, capab):
        if self.check(capab) != True:
            raise Exception('Selected hardware does not support required capability (%d).' % capab)

def devlist(vendor=None, product=None, gps=None):
    '''
    Return device information for all present devices, 
    filtering if requested by vendor and/or product IDs on USB devices, and
    running device fingerprint functions on serial devices.
    @type gps: String
    @param gps: Optional serial device identifier for an attached GPS
    unit. If provided, or if global variable has previously been set, 
    KillerBee skips that device in device enumeration process.
    @rtype: List
    @return: List of device information present.
                For USB devices, get [busdir:devfilename, productString, serialNumber]
                For serial devices, get [serialFileName, deviceDescription, ""]
    '''
    global usbVendorList, usbProductList, gps_devstring
    if gps is not None and gps_devstring is None:
        gps_devstring = gps
    devlist = []

    busses = usb.busses()
    for bus in busses:
        devices = bus.devices
        for dev in devices:
            if ((vendor==None and dev.idVendor in usbVendorList) or dev.idVendor==vendor) \
               and ((product==None and dev.idProduct in usbProductList) or dev.idProduct==product):
                devlist.append([''.join([bus.dirname + ":" + dev.filename]), \
                                  dev.open().getString(dev.iProduct, 50),    \
                                  dev.open().getString(dev.iSerialNumber, 12)])

    seriallist = get_serial_ports()
    for serialdev in seriallist:
        if serialdev == gps_devstring:
            print "kbutils.devlist is skipping GPS device string: %s" % serialdev #TODO remove print, make pass
        elif (isgoodfetccspi(serialdev)):
            devlist.append([serialdev, "GoodFET TelosB/Tmote", ""])
        elif (DEV_ENABLE_FREAKDUINO and isfreakduino(serialdev)):
            devlist.append([serialdev, "Dartmouth Freakduino", ""])
    return devlist

def get_serial_devs():
    global DEV_ENABLE_FREAKDUINO
    #TODO Continue moving code from line 83:89 here, yielding results

def get_serial_ports():
    seriallist = glob.glob("/dev/ttyUSB*") #TODO make cross platform globing/winnt
    return seriallist
    
def isgoodfetccspi(serialdev):
    '''
    Determine if a given serial device is a TelosB/Tmote Sky GOODFET (with CCSPI application).
    @type serialdev: String
    @param serialdev: Path to a serial device, ex /dev/ttyUSB0.
    @rtype: Boolean
    '''
    from GoodFETCCSPI import GoodFETCCSPI
    os.environ["platform"] = "telosb" #set enviroment variable for GoodFET code to use
    gf = GoodFETCCSPI()
    gf.serInit(port=serialdev, attemptlimit=2)
    status = (gf.connected == 1)
    gf.serClose()
    return status
    
def isfreakduino(serialdev):
    '''
    Determine if a given serial device is a Freakduino attached with the right sketch loaded.
    @type serialdev: String
    @param serialdev: Path to a serial device, ex /dev/ttyUSB0.
    @rtype: Boolean
    '''
    s = serial.Serial(port=serialdev, baudrate=57600, timeout=1, bytesize=8, parity='N', stopbits=1, xonxoff=0)
    time.sleep(1.5)
    s.write('SC!V\r')
    time.sleep(1.5)
    #readline should take an eol argument, per:
    # http://pyserial.sourceforge.net/pyserial_api.html#serial.FileLike.readline
    # However, many got an "TypeError: readline() takes no keyword arguments" due to a pySerial error
    # So we have replaced it with a bruteforce method. Old: s.readline(eol='&')
    for i in range(100):
        if (s.read() == '&'): break
    if s.read(3) == 'C!V': version = s.read()
    else: version = None
    s.close()
    return (version is not None)

def search_usb(device, vendor=None, product=None):
    busses = usb.busses()
    for bus in busses:
        dev = search_usb_bus(bus, device)
        if dev != None:
            return (bus, dev)
    return (None, None)

def search_usb_bus(bus, device, vendor=None, product=None):
    global vendorList, productList
    devices = bus.devices
    for dev in devices:
        if ((vendor==None and dev.idVendor in usbVendorList) or dev.idVendor==vendor) \
           and ((product==None and dev.idProduct in usbProductList) or dev.idProduct==product):
            if device == None or (device == (''.join([bus.dirname, ":", dev.filename]))):
                #Populate the capability information for this device later, when driver is initialized
                #print "Choose device", bus.dirname, dev.filename, "to initialize KillerBee instance on."
                return dev
    return None

def hexdump(src, length=16):
    '''
    Creates a tcpdump-style hex dump string output.
    @type src: String
    @param src: Input string to convert to hexdump output.
    @type length: Int
    @param length: Optional length of data for a single row of output, def=16
    @rtype: String
    '''
    FILTER = ''.join([(len(repr(chr(x))) == 3) and chr(x) or '.' for x in range(256)])
    result = []
    for i in xrange(0, len(src), length):
       chars = src[i:i+length]
       hex = ' '.join(["%02x" % ord(x) for x in chars])
       printable = ''.join(["%s" % ((ord(x) <= 127 and FILTER[ord(x)]) or '.') for x in chars])
       result.append("%04x:  %-*s  %s\n" % (i, length*3, hex, printable))
    return ''.join(result)

def randbytes(size):
    '''
    Returns a random string of size bytes.  Not cryptographically safe.
    @type size: Int
    @param size: Length of random data to return.
    @rtype: String
    '''
    return ''.join(chr(random.randrange(0,256)) for i in xrange(size))

def randmac(length=8):
    '''
    Returns a random MAC address using a list valid OUI's from ZigBee device manufacturers.  Data is returned in air-format byte order (LSB first).
    @type length: String
    @param length: Optional length of MAC address, def=8.  Minimum address return length is 3 bytes for the valid OUI.
    @rtype: String
    '''
    # Valid OUI prefixes for MAC addresses
    prefixes = [ "\x00\x0d\x6f",    # Ember
                "\x00\x12\x4b",     # TI
                "\x00\x04\xa3",     # Microchip
                "\x00\x04\x25",     # Atmel
                "\x00\x11\x7d",     # ZMD
                "\x00\x13\xa2",     # MaxStream
                "\x00\x30\x66",     # Cirronet
                "\x00\x0b\x57",     # Silicon Laboratories
                "\x00\x04\x9f",     # Freescale Semiconductor
                "\x00\x21\xed",     # Telegesis
                "\x00\xa0\x50"      # Cypress
                ]

    prefix = prefixes[random.randrange(0, len(prefixes))]
    suffix = randbytes(length-3)
    # Reverse the address for use in a packet
    return ''.join([prefix, suffix])[::-1]

# Do a CRC-CCITT Kermit 16bit on the data given
# Returns a CRC that is the FCS for the frame
#  Implemented using pseudocode from: June 1986, Kermit Protocol Manual
#  See also: http://regregex.bbcmicro.net/crc-catalogue.htm#crc.cat.kermit
def makeFCS(data):
    crc = 0
    for i in xrange(len(data)):
        c = ord(data[i])
		#if (A PARITY BIT EXISTS): c = c & 127	#Mask off any parity bit
        q = (crc ^ c) & 15				#Do low-order 4 bits
        crc = (crc // 16) ^ (q * 4225)
        q = (crc ^ (c // 16)) & 15		#And high 4 bits
        crc = (crc // 16) ^ (q * 4225)
    return pack('<H', crc) #return as bytes in little endian order
