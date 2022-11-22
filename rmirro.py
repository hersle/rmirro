#!/usr/bin/python3

import subprocess
import os
import json
import urllib.request

def pc_run(cmd):
    output = subprocess.getoutput(cmd)
    return output

def rm_run(cmd):
    return pc_run(f"ssh {RM_SSH_NAME} {cmd}")

def ssh_ip():
    return pc_run("ssh remarkable -v exit 2>&1 | grep 'Connecting to' | cut -d' ' -f4") # e.g. 10.11.99.1

RM_SSH_NAME = "remarkable"
RM_SSH_IP = ssh_ip()
RM_CONTENT_PATH = "/home/root/.local/share/remarkable/xochitl"

"""
# Object describing a file on Remarkable and/or PC
class File:
    def __init__(self, rm_path, rm_dict):
        self.rm_path = rm_path # e.g. /Notes/Document.pdf
        self.pc_path = RM_SSH_NAME + "rm_path" # e.g. remarkable/Notes/Document.pdf

        self.is_directory = rm_dict["type"] == "CollectionType"

        self.rm_exists = True # TODO:
        self.rm_atime = rm_dict["lastOpened"] # ms
        self.rm_mtime = rm_dict["lastModified"] # ms

        self.pc_exists = os.path.exists(self.pc_path)
        self.pc_atime = int(os.path.getatime(self.pc_path) * 1000) if self.pc_exists else 0 # ms
        self.pc_mtime = int(os.path.getmtime(self.pc_path) * 1000) if self.pc_exists else 0 # ms
"""

def rmtraversefiles(func, action, skiproot=True, skipfolders=True, skipolder=False):
    pc_run(f"rsync -avz {RM_SSH_NAME}:{RM_CONTENT_PATH}/*.metadata .rmmetadata/")
    mdfilenames = os.listdir(".rmmetadata/")
    files = {
        "": { "visibleName": "", "type": "CollectionType", "children": []}, # start with fictuous root node
    }

    # Build file tree nodes
    for mdfilename in mdfilenames:
        id = mdfilename.removesuffix(".metadata")
        mdfile = open(f".rmmetadata/{mdfilename}", "r")
        file = json.load(mdfile)

        if file["deleted"]:
            continue # skip leftovers from deleted RM files

        file["id"] = id
        file["children"] = []

        if file["type"] == "DocumentType" and not file["visibleName"].endswith(".pdf"):
            file["visibleName"] += ".pdf" # everything should be a PDF after backup
        
        files[id] = file

    # Build file tree edges
    for fileid, file in files.items():
        skip = fileid == "" or file["parent"] == "trash"
        if skip:
            continue
        parentname = file["parent"]
        parent = files[parentname]
        parent["children"] += [fileid]

    def rmolder(file, rm_path):
        if file["type"] == "DocumentType":
            rm_mtime = int(file["lastModified"]) # ms
        else:
            # TODO: can this fail if also pc_mtime = 0 on the directory?
            # TODO: get current time stamp (live on RM) instead?
            rm_mtime = 0 # directories have not stored lastModified 
        pc_path = RM_SSH_NAME + rm_path
        pc_exists = os.path.exists(pc_path)
        pc_mtime = int(os.path.getmtime(pc_path) * 1000) if pc_exists else 0 # ms
        return rm_mtime <= pc_mtime

    def traverse(id, path):
        file = files[id]
        path += file["visibleName"]

        skip = (skiproot and fileid == "") or \
               (skipfolders and file["type"] == "CollectionType") or \
               (skipolder and rmolder(file, path))
        if skip:
            print("SKIP " + path)
        else:
            print(action + " " + path)
            func(file, path)

        for childid in file["children"]:
            traverse(childid, path + "/")
        
    traverse("", "")

def rmlistfiles(verbose=False):
    def rmlistfile(file, rm_path):
        if verbose:
            rm_atime = int(file["lastOpened"])
            rm_mtime = int(file["lastModified"])

            pc_path = RM_SSH_NAME + rm_path
            pc_exists = os.path.exists(pc_path)
            pc_mtime = int(os.path.getmtime(pc_path) * 1000) if pc_exists else 0 # to seconds (as rm_mtime)
            pc_atime = int(os.path.getatime(pc_path) * 1000) if pc_exists else 0
            
            d_mtime = pc_mtime - rm_mtime

            print(f"* RM: last modified {rm_mtime}" + (f" ({-d_mtime} ms newer)" if d_mtime <= 0 else ""))
            print(f"* PC: last modified {pc_mtime}" + (f" ({+d_mtime} ms newer)" if d_mtime >= 0 else ""))
    rmtraversefiles(rmlistfile, "LIST")

def rmpullfiles():
    def rmpullfile(file, rmpath):
        pcpath = RM_SSH_NAME + rmpath
        if file["type"] == "CollectionType":
            pc_run(f"mkdir {pcpath}")
        elif file["type"] == "DocumentType":
            url = f"http://{RM_SSH_IP}/download/{file['id']}/placeholder"
            urllib.request.urlretrieve(url, filename=pcpath)
            atime = int(file["lastOpened"]) / 1000 # s
            mtime = int(file["lastModified"]) / 1000 # s
            os.utime(pcpath, (atime, mtime)) # sync with access/modification times from RM
        else:
            raise f"Unknown file type: {file['type']}"
    rmtraversefiles(rmpullfile, "PULL", skipfolders=False, skipolder=True) # skip files already downloaded
            
if __name__ == "__main__":
    rmlistfiles(verbose=True)
    #rmpullfiles()
