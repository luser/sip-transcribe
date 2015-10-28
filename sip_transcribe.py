#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2015 Ted Mielczarek <ted@mielczarek.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function

from multiprocessing import Event
from Queue import Empty
import argparse
import datetime
import time
import os
import socket
import sys

from application.notification import NotificationCenter
from sipsimple.account import AccountManager, Account
from sipsimple.application import SIPApplication
from sipsimple.storage import MemoryStorage
from sipsimple.configuration.settings import SIPSimpleSettings
from sipsimple.core import SIPURI, SIPCoreError, ToHeader
from sipsimple.lookup import DNSLookup, DNSLookupError
from sipsimple.session import Session
from sipsimple.streams import AudioStream
from sipsimple.threading.green import run_in_green_thread

from recognition import run_recognition, get_parser as base_get_parser

def create_account(settings):
    # Totally guessing here
    local_ip = [(s.connect(('8.8.8.8', 80)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]
    aid = 'transcriber@' + local_ip
    a = Account(aid)
    a.display_name = 'Transcription Bot'
    a.sip.register = False
    a.enabled = True
    a.save()
    settings.default_account = aid
    settings.save()
    return a

class SimpleSIPApplication(SIPApplication):
    def __init__(self, debug=False):
        SIPApplication.__init__(self)
        self.ended = Event()
        self.callee = None
        self.session = None
        self.debug = debug
        notification_center = NotificationCenter()
        notification_center.add_observer(self)

    def call(self, url):
        self.callee = url
        self.start(MemoryStorage())

    @run_in_green_thread
    def _NH_SIPApplicationDidStart(self, notification):
        settings = SIPSimpleSettings()
        # We don't need a microphone
        settings.audio.input_device = None
        settings.audio.alert_device = None
        # Use the default audio output.
        #TODO: allow specifying this somehow?
        #settings.audio.output_device = None
        if self.debug:
            settings.logs.trace_pjsip = True
        account = create_account(settings)
        settings.save()
        try:
            self.callee = ToHeader(SIPURI.parse(self.callee))
        except SIPCoreError:
            print('Specified SIP URI is not valid', file=sys.stderr)
            self.stop()
            return
        try:
            routes = DNSLookup().lookup_sip_proxy(self.callee.uri, ['udp']).wait()
        except DNSLookupError, e:
            print('DNS lookup failed: %s' % str(e), file=sys.stderr)
        else:
            self.session = Session(account)
            self.session.connect(self.callee, routes, [AudioStream()])

    def _NH_SIPSessionGotRingIndication(self, notification):
        pass

    def _NH_SIPSessionDidStart(self, notification):
        pass

    def _NH_SIPSessionDidFail(self, notification):
        print('Failed to connect', file=sys.stderr)
        self.stop()

    def _NH_SIPSessionWillEnd(self, notification):
        pass

    def _NH_SIPSessionDidEnd(self, notification):
        self.stop()

    def _NH_SIPApplicationDidEnd(self, notification):
        self.ended.set()

    def _NH_SIPEngineLog(self, notification):
        print(notification.data.message, file=sys.stderr)

    def _NH_SIPEngineSIPTrace(self, notification):
        print(notification.data.data, file=sys.stderr)

def transcribe(sip_url, max_call_length=3600, **kwargs):
    '''
    Place a SIP call to `sip_url`.
    Yield transcribed text as strings as they are recognized.
    Disconnect the call if it lasts more than `max_call_length` seconds.

    Additional kwargs are passed to run_recognition.
    '''
    # Start the transcription process.
    (p, recognizer_event, text_queue) = run_recognition(**kwargs)
    # Start the SIP call
    application = SimpleSIPApplication()
    application.call(sip_url)
    join_process = True
    try:
        while not application.ended.is_set() and not recognizer_event.is_set():
            try:
                text = text_queue.get(True, 5)
                yield text
            except Empty:
                pass
                # See if we've exceed max_call_length
#                if application.session and application.session.start_time and (datetime.datetime.now() - application.session.start_time).total_seconds() > max_call_length:
#                    application.session.end()
#                    break
    except KeyboardInterrupt:
        join_process = False
    finally:
        recognizer_event.set()
        if join_process:
            p.join()
        if application.session:
            application.session.end()
        application.ended.wait()

def get_parser():
    parser = base_get_parser()
    parser.add_argument('sip_url', help='URL of a SIP session to transcribe')
    parser.add_argument('--debug', action='store_true',
                        help='Output debug logging')
    return parser

def main():
    parser = get_parser()
    args = parser.parse_args()
    kwargs = vars(args)
    for text in transcribe(**kwargs):
        print('%s ' % text)
        sys.stdout.flush()

if __name__ == '__main__':
    main()
