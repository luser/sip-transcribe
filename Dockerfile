FROM ubuntu:15.04
# If host is running squid-deb-proxy on port 8000, populate /etc/apt/apt.conf.d/30proxy
# By default, squid-deb-proxy 403s unknown sources, so apt shouldn't proxy ppa.launchpad.net
RUN awk '/^[a-z]+[0-9]+\t00000000/ { printf("%d.%d.%d.%d\n", "0x" substr($3, 7, 2), "0x" substr($3, 5, 2), "0x" substr($3, 3, 2), "0x" substr($3, 1, 2)) }' < /proc/net/route > /tmp/host_ip.txt
RUN perl -pe 'use IO::Socket::INET; chomp; $socket = new IO::Socket::INET(PeerHost=>$_,PeerPort=>"8000"); print $socket "HEAD /\n\n"; my $data; $socket->recv($data,1024); exit($data !~ /squid-deb-proxy/)' <  /tmp/host_ip.txt \
  && (echo "Acquire::http::Proxy \"http://$(cat /tmp/host_ip.txt):8000\";" > /etc/apt/apt.conf.d/30proxy) \
  && (echo "Acquire::http::Proxy::ppa.launchpad.net DIRECT;" >> /etc/apt/apt.conf.d/30proxy) \
  || echo "No squid-deb-proxy detected on docker host"
ADD http://download.ag-projects.com/agp-debian-gpg.key /tmp/
RUN apt-key add /tmp/agp-debian-gpg.key
RUN echo "deb    http://ag-projects.com/ubuntu vivid main" >> /etc/apt/sources.list
RUN apt-get update && apt-get install -y curl
# Download latest pocketsphinx English language model/HMM
ADD download-pocketsphinx-lm.sh /tmp/
RUN sh /tmp/download-pocketsphinx-lm.sh
RUN apt-get install -y pkg-config build-essential bison python-dev python-pip swig2.0 python-sipsimple python-pyaudio pulseaudio pulseaudio-utils psmisc
ADD install-pocketsphinx.sh /tmp/
RUN sh /tmp/install-pocketsphinx.sh
RUN pip install etherpad_lite
RUN useradd -d /home/user -s /bin/bash -m user
USER user
ENV LD_LIBRARY_PATH=/usr/local/lib
WORKDIR /home/user
ADD run.sh runether.sh sip_transcribe.py sip_transcribe_etherpad.py /home/user/
