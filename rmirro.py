#!/usr/bin/python3

import subprocess
import os
import shutil
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

def rmnewer(file):
    rm_path = file["path"]
    if file["type"] == "DocumentType":
        rm_mtime = int(file["lastModified"]) # ms
    else:
        # TODO: can this fail if also pc_mtime = 0 on the directory?
        # TODO: get current time stamp (live on RM) instead?
        rm_mtime = 0 # directories have not stored lastModified 
    pc_path = RM_SSH_NAME + rm_path
    pc_exists = os.path.exists(pc_path)
    pc_mtime = int(os.path.getmtime(pc_path) * 1000) if pc_exists else 0 # ms
    return rm_mtime > pc_mtime

def download_file(file):
    rmpath = file["path"]
    pcpath = "/tmp/remarkable" + rmpath

    if file["type"] == "CollectionType":
        print("MDIR", file["path"])
        pc_run(f"mkdir {pcpath}")
    elif file["type"] == "DocumentType":
        if rmnewer(file):
            # download
            print("PULL", file["path"])
            url = f"http://{RM_SSH_IP}/download/{file['id']}/placeholder"
            urllib.request.urlretrieve(url, filename=pcpath)
            atime = int(file["lastOpened"]) / 1000 # s
            mtime = int(file["lastModified"]) / 1000 # s
            os.utime(pcpath, (atime, mtime)) # sync with access/modification times from RM
        else:
            # copy cached
            print("SKIP", file["path"])
            pcpath_cached = RM_SSH_NAME + rmpath
            shutil.copy2(pcpath_cached, pcpath)
    else:
        raise f"Unknown file type: {file['type']}"

def download_files(skiproot=True, skipfolders=False, skipolder=False):
    pc_run(f"rm -r /tmp/{RM_SSH_NAME}") # start clean

    dest = f"./{RM_SSH_NAME}_cache/"
    cache = f"./{RM_SSH_NAME}/"
    pc_run(f"rsync -avzd {RM_SSH_NAME}:{RM_CONTENT_PATH}/*.metadata {RM_SSH_NAME}_metadata/")
    mdfilenames = os.listdir(f"{RM_SSH_NAME}_metadata/")
    files = {
        "": { "visibleName": "", "type": "CollectionType", "children": []}, # start with fictuous root node
    }

    # Build file tree nodes
    for mdfilename in mdfilenames:
        id = mdfilename.removesuffix(".metadata")
        mdfile = open(f"{RM_SSH_NAME}_metadata/{mdfilename}", "r")
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

    def traverse(id, path):
        file = files[id]
        path += file["visibleName"]
        file["path"] = path

        download_file(file)

        for childid in file["children"]:
            traverse(childid, path + "/")
        
    traverse("", "")

    # Merge temporary downloaded directory into "actual" Remarkable directory
    output = pc_run(f"rsync -avzUuih --delete /tmp/{RM_SSH_NAME}/ ./{RM_SSH_NAME}/")
    print(output)
    pc_run(f"rm -r /tmp/{RM_SSH_NAME}") # start clean

if __name__ == "__main__":
    download_files()
