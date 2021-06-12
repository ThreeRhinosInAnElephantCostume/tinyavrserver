% tinyavrprogrammer(7) 1.0.0

# NAME

tinyavrprogrammer — an AVRDUDE-compatible HVSP programming suite.

# SYNOPSIS

Consider moving your avrdude executable with tinyavroverride. You can rename the original executable to _avrdude to retain non-HVSP programming capability on other hardware.
**tiynavroverride** [*valid AVRDUDE program commands*]
See AVRDUDE(1) man page for more information.


# DESCRIPTION

This manual covers the software, hardware, and firmware aspects of the programmer.

This man page may refer to the programmer as the "PROG" and to the microcontroller being programmed as the "MCU". The development machine and the firmware running on it might be reffered to as the "PC".

## **tinyavrserver**

is a firmware library that contains an **AVRDUDE(1)**-compatible command interpreter.

*main(targetchip:str)* is a high-level interface capable of parsing **AVRDUDE(1)** commands. However the library contains a series of lower-level abstrations that can be used to implement a different higher-level interface.

*prog* is a class containing the state of the programmer along with the functions required for low-level operation. The initializer will look for a device that matches the device signature and connect to it.
Any higher level wrapper (like the *main()* function should call *release()* to deinitialize the usb connection.

## Write Operations

A typical write operation (as exemplified by upload_flash) should look as follows:

1. Create a *prog* object.
2. Power on the MCU using *prog.cmd_power_on()*.
3. Load MCU information using *prog.cmd_check()*.
4. Erase the chip using *prog.cmd_chip_erase()*.
5. Write the desired data into the programmer's internal memory using *prog.cmd_write_data(dest:int, data:bytes, len:int)->bytes*. Do note that this can only be done 60 bytes at a time.
6. Verify the data by generating a hash with *prog.cmd_hash_data(start, end)* and then comparing it with the hash generated with *hash(data: bytes)->bytes*, which hashes given data with an algorithm matching that of the programmer.
7. Write into the MCU (see the source code for a complete list of operations).
8. Read back the data from the MCU into the programmer's internal memory (see the source code for a complete list of operations).
9. Repeat step 6.
10. Power down the MCU with *prog.cmd_power_off()*
11. Release the USB resources with *prog.release()*
12. Ensure that the *prog* object is not used again.


## Read Operations

A typical read operation (as exemplified by read_flash) should look as follows:

1. Create a *prog* object.
2. Power on the MCU using *prog.cmd_power_on()*.
3. Load MCU information using *prog.cmd_check()*.
4. Read the desired MCU data into the programmer's internal memory. (see the source code for a complete list of operations).
5. Read from the programmer's internal memory using *prog.cmd_read_data(dest:int, len:int)->bytes*. Do note that this can only be done 60 bytes at a time.
6. Verify the data by generating a hash with *prog.cmd_hash_data(start, end)* and then comparing it with the hash generated with *hash(data: bytes)*, which hashes given data with an algorithm matching that of the programmer.
7. Power down the MCU with *prog.cmd_power_off()*
8. Release the USB resources with *prog.release()*
9. Ensure that the *prog* object is not used again.

All commands can result in assertion errors which should be handled gracefully.

The library also contains a series of mid-level functions for operating on flash and EEPROM as well as a few test functions used for testing.

## **tinyavroverride**

is a script using **tinyavrserver** that can pretend to be **AVRDUDE(1)**, and will even launch it if it's asked to program a chip not supported by **tinyavrprogrammer**

Consider moving your avrdude executable with tinyavroverride. You can rename the original executable to _avrdude to retain non-HVSP programming capability on other hardware.


## **tinyprogrammer**

is the software controlling the hardware portion of the programmer.

It's a C++ program that incorporates both an usb-controlled programming interface (core0) and a 250KHz boost-converter controller and monitor (core1).

An excessive amount of effort has been put into ensuring safety of the circuit, especially the boost converter. The programmer will not allow any commands until both the boost voltage, and the supply voltage are within specification. If the specification (+ a large safety margin) are exceeded while the MCU is on, an emergency shutdown will occur, requiring a manual power reset to resume operation.

The programmer will shut off the MCU after a few seconds of inactivity. This should never happen unless the firmware fails to shut it down.

See globals.hpp to see the programmer's settings.

## Hardware

An RPI PICO based circuit diagram should be provided with the firmware. The hardware uses a 250KHz boost-converter to generate the 12V required to enter the HVSP mode. See the [BUGS](#BUGS) section for the many issues with this design.

The circuit contains 6 different channels that have to be level-shifted.
The 5V MCU power is togged using an NPN+PNP trainsistor pair.
The 12V signal is isolated using an optoisolator.
The three PROG -> MCU lines are toggled using a single N-CHANNEL MOSFET each.
The single MCU -> PROG line is isolated using an NPN transistor.

An RGB LED is provided to indicate various states of the programmer. The RGB values used to generate the PWM signals driving it can be found in globals.hpp.

By default, ADC channel 0 is used for reading the boost converter voltage and channel 1 is used to read VBUS.

**WARNING:** globals.hpp contains calibration values for the ADC (offset for each channel). Those are based off of a single RPI PICO used in the programmer's development and might need to be revised.

### Pin mapping

The globals.hpp file of the tinyprogrammer contains all of the pin constants

- **SCI** — *PIN 17* — Serial clock input
- **SDI** — *PIN 15* — Serial data input
- **SII** — *PIN 14* — Serial instruction input
- **SDO** — *PIN 12* — Serial data output

- **POWER** — *PIN 16* — toggles power to the MCU
- **PULSE** — *PIN 13* — the pwm source that drives the boost converter
- **HIGHVOLT** — *PIN 18* — toggles the connection between 12V line and the MCU's reset pin.

- **RED** — *PIN 9* — the red PWM channel of the RGB LED indicator.
- **GREEN** — *PIN 8* — the green PWM channel of the RGB LED indicator.
- **BLUE** — *PIN 7* — the blue PWM channel of the RGB LED indicator.

## Communication Protocol

The firmware communicates with the programmer over USB, the packet size is 64 bytes, however this could probably be extended.

The programmer has a 128kB buffer that it uses to store intermediate data.

## Supported Microcontrollers

The following microcontrollers are currently supported. The support can be easily extended to other microcontrollers, as discussed later.

- **ATTiny85**
- **ATTiny45**
- **ATTiny25**

## Extending support

### - **tinyavroverride.py**

*chips* contains the list of matches that determines whether to use tinyavrserver. See AVRDUDE(1) for chip identifiers.

### - **tinyprogrammer/globals.hpp**

the *CHIP_ID* enum contains the IDs of the supported MCUs.

*info* contains the MCU information in the following format:

1. *strname* — the name used by the firmware in its output messages.
2. *id* — the CHIP_ID associated with the MCU.
3. *signature* — the 3-byte signature. See the documentation for the relevant MCU.
4. *word_bytes* — the number of bytes per word,  typically 2.
5. *flash_words* — number of words of flash. See the documentation for the relevant MCU.
6. *flash_page_Words* — number of flash words per page.
7. *eeprom_page_bytes* — number of EEPROM bytes per page.
8. *eeprom_page_num* — number of EEPROM pages.

# BUGS

The way the programmer handles reading fuses does not account for MCUs that have less or more than 3. This should work fine with the ATTinyx5 and ATtinyx4 series, but might be an issue with some of the older ATTiny MCUs. This shouldn't require much effort to fix if it does become an issue.

# CAVEATS

## Software

The way the programmer handles reading fuses does not account for MCUs that have less or more than 3. This should work fine with the ATTinyx5 and ATtinyx4 series, but might be an issue with some of the older ATTiny MCUs. This shouldn't require much effort to fix if it does become an issue.

The programmer can only read/write up to 128kB of data at a time. The firmware does not account for the possibility of a larger operation. There are currently no HVSP microcontrollers that would require a greater amount of RAM.

The hash function used for verifying data is weak, it's a simple series XORs.

The USB packet size (64B) is needlessly small.

The HVSP protocol is implemented through bitbanging. This could be replaced with PIO.

## Hardware

The boost-converter design is flawed and incapable of supplying more than ~30mA. This is more than enough for the protocol. One relatively simple improvement would involve replacing the switching NPN transistor with a MOSFET and increasing the operating frequency. 

I would be much simpler to use opto-isolation for all channels instead of using 3 different methods.

# LICENCE

This manual, as well as all of the tinyavrprogrammer components described here 

# SEE ALSO

**AVRDUDE(1)**