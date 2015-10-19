#!/bin/sh

set -e

test -z $1 && exit 1;

export LD_LIBRARY_PATH=/usr/local/lib
# Start pulseaudio and load a null sink
pulseaudio --fail --daemonize --start
pactl load-module module-null-sink sink_name="grab"
pactl list short sinks
python `dirname $0`/sip_transcribe_etherpad.py \
 --hmm=/opt/pocketsphinx/model/en-us/en-us-8khz \
 --lm=/opt/pocketsphinx/model/en-us/en-us.lm.bin \
 $*
pulseaudio --kill
