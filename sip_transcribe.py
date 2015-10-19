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

from multiprocessing import Process, Event, Queue
from Queue import Empty
import argparse
import datetime
import sys
import time
import os
import socket
import sys
from threading import Event

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

def do_recognition(queue, event, max_no_speech=120, debug=False,
                   hmm='/usr/local/share/pocketsphinx/model/en-us/en-us',
                   lm='/usr/local/share/pocketsphinx/model/en-us/en-us.lm.bin',
                   cmudict='/usr/local/share/pocketsphinx/model/en-us/cmudict-en-us.dict'):
    '''
    Read audio from the system default recording device and feed it to
    pocketsphinx. Put recognized text in `queue`. Shut down if `event`
    is set. If no speech is detected for `max_no_speech` seconds, set
    `event` and quit.
    '''
    from pocketsphinx import Decoder
    import pyaudio
    if not debug:
        # PortAudio is chatty on startup.
        f = open(os.devnull, 'wb')
        os.dup2(f.fileno(), sys.stderr.fileno())
    config = Decoder.default_config()
    config.set_string('-hmm', hmm)
    config.set_string('-lm', lm)
    config.set_string('-dict', cmudict)
    if not debug:
        config.set_string('-logfn', '/dev/null')
    decoder = Decoder(config)
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
    stream.start_stream()
    in_speech_bf = True
    no_speech_timer = None
    now_in_speech = False
    decoder.start_utt()
    try:
        while not event.is_set() and stream.is_active():
            buf = stream.read(1024)
            if buf:
                decoder.process_raw(buf, False, False)
                now_in_speech = decoder.get_in_speech()
                if debug and now_in_speech:
                    print('Found speech', file=sys.stderr)
                if now_in_speech != in_speech_bf:
                    in_speech_bf = now_in_speech
                    if not in_speech_bf:
                        if debug:
                            print('Processing speech', file=sys.stderr)
                        # No speech, but there was speech before, so, process.
                        decoder.end_utt()
                        try:
                            speech = decoder.hyp().hypstr
                            if speech != '':
                                if debug:
                                    print('Speech: ' + speech, file=sys.stderr)
                                queue.put_nowait(speech)
                        except AttributeError:
                            pass
                        decoder.start_utt()
                    else:
                        # Got some speech, reset timer.
                        no_speech_timer = None
            else:
                if debug:
                    print('No audio', file=sys.stderr)
                # Wait a bit...
                event.wait(0.1)
            if not now_in_speech:
                if no_speech_timer is None:
                    no_speech_timer = datetime.datetime.now()
                elif (datetime.datetime.now() - no_speech_timer).total_seconds() > max_no_speech:
                    if debug:
                        print('No speech, timing out', file=sys.stderr)
                    event.set()
    except KeyboardInterrupt:
        pass
    finally:
        if stream.is_active():
            stream.stop_stream()
        stream.close()

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

    Additional kwargs are passed to do_recognition.
    '''
    # Start the transcription process.
    recognizer_event = Event()
    text_queue = Queue()
    p = Process(target=do_recognition, args=(text_queue, recognizer_event), kwargs=kwargs)
    p.start()
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
    parser = argparse.ArgumentParser(description='Transcribe SIP session')
    parser.add_argument('sip_url', help='URL of a SIP session to transcribe')
    parser.add_argument('--debug', action='store_true',
                        help='Output debug logging')
    parser.add_argument('--hmm',
                        default='/usr/local/share/pocketsphinx/model/en-us/en-us',
                        help='Path to a pocketsphinx HMM data directory')
    parser.add_argument('--lm',
                        default='/usr/local/share/pocketsphinx/model/en-us/en-us.lm.bin',
                        help='Path to a pocketsphinx language model file')
    parser.add_argument('--cmudict',
                        default='/usr/local/share/pocketsphinx/model/en-us/cmudict-en-us.dict',
                        help='Path to a pocketsphinx CMU dictionary file')
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
