#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (c) 2017, Emmanuel Blot <emmanuel.blot@free.fr>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the Neotion nor the names of its contributors may
#       be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL NEOTION BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

from doctest import testmod
from os import environ
from multiprocessing import Process
from pyftdi import FtdiLogger
from pyftdi.serialext import serial_for_url
from random import choice, seed
from string import printable
from sys import modules, stdout
from time import sleep
import logging
import unittest


class UartTestCase(unittest.TestCase):
    """FTDI UART driver test case

       Simple test to demonstrate UART feature.

       You need a FTDI device that support at least two serial ports to run
       this test.

       Do NOT run this test if you use FTDI port A as an SPI or I2C
       bridge -or any unsupported setup!! You've been warned.
    """

    COUNT = 512

    @classmethod
    def setUpClass(cls):
        seed()

    def test_uart_cross_talk_sp(self):
        something_out = self.generate_bytes()
        """Exchange a random byte stream between the two first UART interfaces
           of the same FTDI device, from the same process

           This also validates PyFtdi support to use several interfaces on the
           same FTDI device from the same Python process
        """
        urla = environ.get('FTDI_DEVICE', 'ftdi://ftdi:2232h/1')
        urlb = self.build_next_url(urla)
        porta = serial_for_url(urla, baudrate=1000000)
        portb = serial_for_url(urlb, baudrate=1000000)
        try:
            if not porta.is_open:
                porta.open()
            if not portb.is_open:
                portb.open()
            porta.timeout = 1.0
            portb.timeout = 1.0
            something_out = self.generate_bytes()
            porta.write(something_out)
            something_in = portb.read(len(something_out))
            self.assertEqual(len(something_in), len(something_out))
            self.assertEqual(something_in, something_out)
            something_out = self.generate_bytes()
            portb.write(something_out)
            something_in = porta.read(len(something_out))
            self.assertEqual(len(something_in), len(something_out))
            self.assertEqual(something_in, something_out)
        finally:
            porta.close()
            portb.close()

    def test_uart_cross_talk_mp(self):
        urla = environ.get('FTDI_DEVICE', 'ftdi://ftdi:2232h/1')
        urlb = self.build_next_url(urla)
        something_out = self.generate_bytes()
        proca = Process(target=self._cross_talk_write_then_read,
                        args=(urla, something_out))
        procb = Process(target=self._cross_talk_read_then_write,
                        args=(urlb, something_out))
        # start B first to ensure RX port is open before TX port starts
        # emitting
        procb.start()
        sleep(0.25)
        proca.start()
        proca.join(2)
        procb.join(2)
        # although the failure is reported (and traceback shown) in the
        # subprocess, we still need to fail the main process test in this case
        exita = proca.exitcode
        exitb = procb.exitcode
        self.assertEqual(exita, 0)
        self.assertEqual(exitb, 0)

    def _cross_talk_write_then_read(self, url, refstream):
        port = serial_for_url(url, baudrate=1000000)
        try:
            if not port.is_open:
                port.open()
            port.timeout = 5.0
            port.write(refstream)
            instream = port.read(len(refstream))
            self.assertEqual(len(instream), len(refstream))
            # we expect the peer to return the same stream, inverted
            localstream = bytes(reversed(instream))
            self.assertEqual(localstream, refstream)
        finally:
            port.close()

    def _cross_talk_read_then_write(self, url, refstream):
        port = serial_for_url(url, baudrate=1000000)
        try:
            if not port.is_open:
                port.open()
            port.timeout = 5.0
            instream = port.read(len(refstream))
            self.assertEqual(len(instream), len(refstream))
            self.assertEqual(instream, refstream)
            # the peer expect us to return the same stream, inverted
            outstream = bytes(reversed(instream))
            port.write(outstream)
        finally:
            port.close()

    @classmethod
    def generate_bytes(cls, count=0):
        return ''.join([choice(printable)
                        for x in range(count or cls.COUNT)]).encode()

    @classmethod
    def build_next_url(cls, url):
        iface = int(url[-1])
        iface = (iface + 1) % 3
        return '%s%d' % (url[:-1], iface)


def suite():
    suite_ = unittest.TestSuite()
    suite_.addTest(unittest.makeSuite(UartTestCase, 'test'))
    return suite_


if __name__ == '__main__':
    testmod(modules[__name__])
    FtdiLogger.log.addHandler(logging.StreamHandler(stdout))
    level = environ.get('FTDI_LOGLEVEL', 'info').upper()
    try:
        loglevel = getattr(logging, level)
    except AttributeError:
        raise ValueError('Invalid log level: %s', level)
    FtdiLogger.set_level(loglevel)
    unittest.main(defaultTest='suite')
