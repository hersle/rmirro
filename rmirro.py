#!/usr/bin/python3

import subprocess
import os
import shutil
import json
import urllib.request
import time
import uuid

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

PC_LAST_SYNC_PATH = RM_SSH_NAME + "/.last_sync"

# TODO: what if trying to overwrite a written note with a PDF?

def read_last_sync_time():
    if os.path.exists(PC_LAST_SYNC_PATH):
        with open(PC_LAST_SYNC_PATH, "r") as file:
            last_sync = int(file.read())
    else:
        last_sync = 0
    return last_sync

def write_last_sync_time(last_sync=int(time.time()*1000)):
    with open(PC_LAST_SYNC_PATH, "w") as file:
        file.write(str(last_sync) + "\n")

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

def download_file(file, pcpath):
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
    last_sync = read_last_sync_time()

    dest = f"./{RM_SSH_NAME}_cache"
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

        if file["deleted"] or file["parent"] == "trash":
            continue # skip leftovers from deleted RM files

        file["id"] = id
        file["children"] = []

        if file["type"] == "DocumentType" and not file["visibleName"].endswith(".pdf"):
            file["visibleName"] += ".pdf" # everything should be a PDF after backup
        
        files[id] = file

    # Build file tree edges
    for fileid, file in files.items():
        skip = fileid == ""
        if skip:
            continue
        parentname = file["parent"]
        parent = files[parentname]
        parent["children"] += [fileid]

    def rm_files(id="", path="/"):
        file = files[id]
        file["path"] = path

        yield file

        for childid in file["children"]:
            child = files[childid]
            childpath = path + ("" if path[-1] == "/" else "/") + child["visibleName"]
            yield from rm_files(childid, childpath)

    def pc_paths(path=RM_SSH_NAME, skip_root=True, skip_hidden=True, top_down=False):
        def pc_paths_dir(dir, files):
            skip = skip_root and dir == RM_SSH_NAME
            if not skip:
                yield dir

        def pc_paths_files(dir, files):
            for file in files:
                filepath = dir + "/" + file
                skip = skip_hidden and file[0] == "."
                if not skip:
                    yield filepath
            
        for dir, _, files in os.walk(f"{RM_SSH_NAME}", topdown=top_down):
            if top_down:
                # directories before files
                yield from pc_paths_dir(dir, files)
                yield from pc_paths_files(dir, files)
            else:
                # files before directories
                yield from pc_paths_files(dir, files)
                yield from pc_paths_dir(dir, files)

    print("Iterating over RM files:")
    rm_files_by_pc_path = {}
    for rm_file in rm_files():
        pc_path = RM_SSH_NAME + rm_file["path"]
        pc_exists = os.path.exists(pc_path)
        rm_mtime = 0 if rm_file["path"] == "/" else int(rm_file["lastModified"])
        pc_mtime = int(os.path.getmtime(pc_path) * 1000) if pc_exists else 0
        if not pc_exists or rm_mtime > pc_mtime:
            download_file(rm_file, pc_path)
        rm_files_by_pc_path[pc_path] = rm_file

    print("Iterating over PC files:")
    for pc_path in pc_paths(skip_root=True, skip_hidden=True, top_down=False):
        is_dir = is_directory(pc_path)
        is_root = pc_path == RM_SSH_NAME

        rm_exists = pc_path in rm_files_by_pc_path
        rm_file = rm_files_by_pc_path[pc_path] if rm_exists else None
        pc_parent_path = None if is_root else os.path.dirname(pc_path)
        if pc_parent_path == RM_SSH_NAME:
            pc_parent_path += "/" # TODO: remove special case
        rm_parent_file = None if is_root else rm_files_by_pc_path[pc_parent_path]
        rm_mtime = 0 if not rm_exists else int(rm_file["lastModified"])
        pc_mtime = int(os.path.getmtime(pc_path) * 1000)
        if rm_exists and pc_mtime > rm_mtime and not is_dir:
            rm_file = upload_file(pc_path, rm_file, rm_parent_file) #
        elif not rm_exists:
            # TODO: check prev sync time, then delete or upload
            diff = pc_mtime - last_sync
            print(diff / 1000, "sec")
            if pc_mtime > last_sync:
                rm_file = upload_file(pc_path, rm_file, rm_parent_file) #
            else:
                delete_file_pc(pc_path)
        rm_files_by_pc_path[pc_path] = rm_file
        # TODO: add file to rm_files_by_pc_path

    #print("Restarting RM interface")
    #rm_run("systemctl restart xochitl")

    write_last_sync_time()

    print("Complete")

def write_file(path, text, transfer=False):
    with open("/tmp/rmirro/" + path, "w") as file:
        file.write(text)
    print("wrote", path)

    if transfer:
        # TODO: reuse transfered metadata files?
        pc_run("scp /tmp/rmirro/{path} {RM_SSH_NAME}:{RM_CONTENT_PATH}/{path}")
        print("transfered", path)

def write_content(id):
    pass # TODO: needed?

def write_metadata(id, metadata):
    write_file(f"{id}.metadata", json.dumps(metadata, indent=4))

def read_metadata(id):
    mdfile = open(f"{RM_SSH_NAME}_metadata/{id}.metadata", "r")
    return json.load(mdfile)

# Create file (including directories)
def create_file(path, parent):
    curtime = int(time.time() * 1000) # ms
    filename = os.path.basename(path) # e.g. "document.pdf"
    name, ext = os.path.splitext(filename) # e.g. ("document", ".pdf")
    print(name, ext)

    metadata = {
        "visibleName": name,
        "parent": parent["id"],
        "lastModified": str(curtime),
        "modified": False,
        "metadatamodified": False,
        "deleted": False,
        "pinned": False,
        "synced": False,
        "version": 0,
    }
    if ext == "": # directory
        metadata["type"] = "CollectionType"
    elif ext == ".pdf":
        metadata["type"] = "DocumentType"
        metadata["lastOpened"] = metadata["lastModified"]
    else:
        raise "Unknown filetype: " + ext

    #content = {"tags": []}
    id = uuid.uuid4()

    # TODO: generate id and write file
    # TODO: move files to RM
    #write_metadata(id, metadata)
    #write_file(f"{id}.metadata", json.dumps(metadata, indent=4) + "\n")
    #write_file(f"{id}.content", json.dumps(content, indent=4).replace("[]", "[\n    ]") + "\n")
    # TODO: must also return file and add to my tree
    return metadata

def update_file(file):
    # TODO: upload file, and update metadata
    # TODO: update metadata

    # store needed "extra" metadata
    id = file["id"]
    mtime = int(os.path.getmtime(RM_SSH_NAME + file["path"]) * 1000) # ms

    # re-read file with original metadata
    file = read_metadata(id)
    
    # modify relevant metadata
    # TODO: does other metadata or other files need to be modified?
    file["lastModified"] = str(mtime)
    file["lastOpened"] = str(mtime)
    file["synced"] = False

    #write_metadata(id, metadata)

    # TODO: move to RM
    # TODO: also move the actual file

def is_directory(path):
    return path[-4:] not in [".pdf"]

def delete_file_pc(pc_path):
    print("RMPC", pc_path)
    if is_directory(pc_path):
        os.rmdir(pc_path)
    else:
        os.remove(pc_path)

def upload_file(pc_path, rm_file, rm_parent_file):
    print("PUSH", pc_path)

    filename = os.path.basename(pc_path) # e.g. "document.pdf"
    name, ext = os.path.splitext(filename) # e.g. ("document", ".pdf")
    assert ext in ["", ".pdf"], f"Unknown filetype: {ext}"
    pc_mtime = int(os.path.getmtime(pc_path) * 1000)

    if rm_file is None:
        id = uuid.uuid4()
        rm_file = {
            "visibleName": name,
            "parent": rm_parent_file["id"] if "id" in rm_parent_file else "", # TODO: rather if parent is root
            "modified": False,
            "metadatamodified": False,
            "deleted": False,
            "pinned": False,
            "version": 0,
        }
        if ext == "": # directory
            rm_file["type"] = "CollectionType"
        elif ext == ".pdf":
            rm_file["type"] = "DocumentType"
            rm_file["lastOpened"] = str(pc_mtime)
    else:
        id = rm_file["id"]
        rm_file = read_metadata(id)

    rm_file["lastModified"] = str(pc_mtime)
    rm_file["synced"] = False

    # TODO: write first,

    # TODO: add id, AFTER writing file
    rm_file["id"] = id
    return rm_file

def upload_files(files):
    files_by_path = {file["path"]: file for id, file in files.items()}

    for dirpath, dirs, files in os.walk(f"{RM_SSH_NAME}"):
        rm_path = dirpath[len(f"{RM_SSH_NAME}"):]
        rm_parent_id = "" if dirpath == "/" else files_by_path
        print(dirpath)
        if rm_path != "" and not rm_path in files_by_path:
            # directory does not exist on remarkable
            # TODO: create t
            #create_directory(0)
            print(f"CREATE DIR: {rm_path}")

        for file in files:
            filepath = dirpath + "/" + file
            rm_path = filepath[len(f"{RM_SSH_NAME}"):]
            if rm_path in files_by_path:
                # file already exists on remarkable
                # TODO: update file if outdated
                print(f"UPDATE IF OUTDATED: {rm_path}")
                pass
            else:
                # file does not exist on remarkable
                # TODO: create file
                print(f"CREATE FILE: {rm_path}")
                pass

    # TODO: restart xochitl thing

if __name__ == "__main__":
    #create_file("/a/B/c.pdf", {"id": "cjfdks"})
    #upload_files(files)

    files = download_files()
