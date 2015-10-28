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

import argparse
import datetime
import os
import sys

from multiprocessing import Process, Event, Queue
from Queue import Empty

def recognition_worker(queue, event, max_no_speech=120, debug=False,
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

def run_recognition(**kwargs):
    '''
    Run PocketSphinx recognition in a background process on the default audio
    input device. `kwargs` will be passed to `recognition_worker`.
    Return (process, event, queue). Recognized text will be posted to `queue`,
    `event` can be set to terminate the recognition process.
    '''
    event = Event()
    queue = Queue()
    p = Process(target=recognition_worker, args=(queue, event), kwargs=kwargs)
    p.start()
    return (p, event, queue)

def get_parser():
    parser = argparse.ArgumentParser(description='Recognize speech from audio')
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
    (p, event, queue) = run_recognition(**vars(args))
    join_process = True
    try:
        while not event.is_set():
            try:
                text = queue.get(True, 5)
                print(text)
            except Empty:
                pass
    except KeyboardInterrupt:
        join_process = False
    finally:
        event.set()
        if join_process:
            p.join()

if __name__ == '__main__':
    main()
