This repository contains a pair of scripts: one to do live transcription of a
SIP call using Pocketsphinx, and one to do that and update an Etherpad Lite
pad with the transcript.

The dependencies are a bit fiddly, so a Dockerfile is provided to build a
container with a usable environment. The Etherpad transcription depends on [an unlanded change to Etherpad Lite](https://github.com/luser/etherpad-lite/tree/append-text).

This software is provided under the GPL. See [COPYING](COPYING).
