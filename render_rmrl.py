#!/usr/bin/python3

# This method uses the third-party renderer rmrl to render reMarkable documents locally on the computer.
# It downloads the raw reMarkable files to the computer and renders them locally.
#
# It requires the Python module rmrl (https://github.com/rschroll/rmrl/) and SSH access to the reMarkable (to download the raw files), but no USB connection.
# It is not extensively tested, and fails in some cases.
#
# Thanks to Ph-St for contributing this renderer (https://github.com/hersle/rmirro/issues/10)!

import sys
import os.path
import subprocess
from rmrl import render

def render_rmrl(input, output):
    stream = render(input)
    with open(output, "wb") as out_file:
        out_file.write(stream.read())

if __name__ == "__main__":
    args = sys.argv[1:]
    assert len(args) == 2, "usage: render_rmrl.py infile outfile"

    infile = args[0]
    outfile = args[1]

    status = render_rmrl(infile, outfile)
    
    exit(status)
