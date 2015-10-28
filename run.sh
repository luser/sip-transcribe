#!/bin/sh

set -e

test -z $1 && exit 1;

export LD_LIBRARY_PATH=/usr/local/lib
python `dirname $0`/sip_transcribe.py \
 --hmm=/opt/pocketsphinx/model/en-us/en-us-8khz \
 --lm=/opt/pocketsphinx/model/en-us/en-us.lm.bin \
 $*
