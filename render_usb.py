#!/usr/bin/python3

# This is the default method to render reMarkable documents to PDFs.
# It renders the document on the reMarkable using its official renderer.
# It then transfers the PDF to the computer using the USB web interface.
#
# The reMarkable must be connected through USB, and the USB web interface must be enabled!

import sys
import urllib.request

if __name__ == "__main__":
    args = sys.argv[1:]
    assert len(args) == 2, "usage: render_usb.py uuid outfile" # require UUID and output file

    uuid = args[0]
    outfile = args[1]

    url = f"http://10.11.99.1/download/{uuid}/placeholder"
    try:
        urllib.request.urlretrieve(url, filename=outfile)
        exit(0) # success
    except Exception as e:
        print(f"Could not download {url} from reMarkable USB web interface")
        exit(1) # failure
