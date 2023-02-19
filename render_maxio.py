#!/usr/bin/python3

# This method uses the third-party maxio renderer to render reMarkable documents locally on the computer.
# It downloads the raw reMarkable files to the computer and renders them locally.
#
# It requires maxio and SSH access to the reMarkable (to download the raw files), but no USB connection.
#
# As of 2017-02-14, it produces worse results than the official reMarkable renderer.
# It fails in some cases, particularly for highlighted documents of the new v3 format.
# It was tested using this fork of maxio, paired with this fork of rmscene (for parsing v3 formatted documents):
# * https://github.com/hersle/maxio/tree/overlay
# * https://github.com/hersle/rmscene/tree/anysize
#
# To use a different third-party renderer, wrap it in a script with call signature like this one!

import sys
import os.path
import subprocess

if __name__ == "__main__":
    args = sys.argv[1:]
    assert len(args) == 2, "usage: render_maxio.py infile outfile"

    infile = args[0]
    outfile = args[1]

    maxio_rmtool_path = os.environ["HOME"] + "/Remarkable/maxio/rm_tools/rmtool.py" # NOTE: modify depending on where maxio is installed!
    status, _ = subprocess.getstatusoutput(f"{maxio_rmtool_path} convert \"{infile}\" \"{outfile}\"") # convert raw files to PDF
    exit(status)
