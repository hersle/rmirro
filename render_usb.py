#!/usr/bin/python3

# This is the default method to render reMarkable documents to PDFs.
# It renders the document on the reMarkable using its official renderer.
# It then transfers the PDF to the computer using the USB web interface.
#
# The reMarkable must be connected through USB, and the USB web interface must be enabled!

import sys
import os.path
import urllib.request

if __name__ == "__main__":
    args = sys.argv[1:]
    assert len(args) == 2, "usage: render_usb.py infile outfile"

    infile = args[0]
    outfile = args[1]

    # RM file stems end with their UUID:
    # "abuse" this to render and download it from the USB web interface
    uuid = os.path.basename(infile)
    url = f"http://10.11.99.1/download/{uuid}/placeholder"
    try:
        urllib.request.urlretrieve(url, filename=outfile)
        exit(0) # success
    except Exception as e:
        raise(RuntimeError(f"Could not download {url} from reMarkable USB web interface. Make sure that Settings > Storage > USB web interface is enabled"))
        exit(1) # failure
