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
from urlparse import urljoin
from etherpad_lite import EtherpadLiteClient

from sip_transcribe import transcribe
from sip_transcribe import get_parser as base_get_parser

def transcribe_to_etherpad(sip_url, etherpad_url, api_key_file, **kwargs):
    api_url = urljoin(etherpad_url, '/api')
    pad_id = etherpad_url.split('/')[-1]

    apikey = open(api_key_file, 'rb').read()
    c = EtherpadLiteClient(base_url=api_url, api_version='1.2.13', base_params={'apikey': apikey})
    for text in transcribe(sip_url, **kwargs):
        c.appendText(padID=pad_id, text=' ' + text)


def get_parser():
    parser = base_get_parser()
    parser.add_argument('etherpad_url',
                        help='URL of an Etherpad Lite pad in which to put transcription')
    parser.add_argument('api_key_file',
                        help='Path to a file containing Etherpad Lite API key')
    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()
    kwargs = vars(args)
    transcribe_to_etherpad(**kwargs)


if __name__ == '__main__':
    main()
