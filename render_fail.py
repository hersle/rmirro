#!/usr/bin/python3

# This is a dummy renderer that deliberately always fails without producing a PDF file.

import sys

if __name__ == "__main__":
    args = sys.argv[1:]
    assert len(args) == 2, "usage: render_fail.py infile outfile"

    infile = args[0]
    outfile = args[1]

    raise(RuntimeError(f"Refusing to render {infile}"))

    exit(1) # fail
