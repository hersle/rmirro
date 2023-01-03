#!/usr/bin/python3

import subprocess
import os
import shutil
import json
import urllib.request
import time
import datetime
import uuid

DRY_RUN = False

def pc_run(cmd):
    output = subprocess.getoutput(cmd)
    return output

def rm_run(cmd):
    return pc_run(f"ssh {RM_SSH_NAME} {cmd}")

RM_SSH_NAME = "remarkable"
RM_SSH_IP = pc_run(f"ssh {RM_SSH_NAME} -v exit 2>&1 | grep 'Connecting to' | cut -d' ' -f4") # e.g. 10.11.99.1
RM_CONTENT_PATH = "/home/root/.local/share/remarkable/xochitl"

print(f"Connected to {RM_SSH_NAME} at {RM_SSH_IP}")

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
    #print((rm_mtime - pc_mtime) / 1000 / 3600 / 24)
    return rm_mtime > pc_mtime

def download_file(file, pcpath):
    if file["type"] == "CollectionType":
        if os.path.exists(pcpath):
            print("SKIP", file["path"])
        else:
            print("MDIR", file["path"])
            if DRY_RUN:
                return
            pc_run(f"mkdir \"{pcpath}\"")
            mtime = int(file["lastModified"]) / 1000 # s
            os.utime(pcpath, (mtime, mtime)) # sync with access/modification times from RM
    elif file["type"] == "DocumentType":
        if rmnewer(file):
            # download
            print("PULL", file["path"])
            if DRY_RUN:
                return
            try:
                url = f"http://{RM_SSH_IP}/download/{file['id']}/placeholder"
                urllib.request.urlretrieve(url, filename=pcpath)
                atime = int(file["lastOpened"]) / 1000 # s
                mtime = int(file["lastModified"]) / 1000 # s
                os.utime(pcpath, (atime, mtime)) # sync with access/modification times from RM
            except Exception as e:
                print(f"ERROR Could not download {url} from {RM_SSH_NAME}.")
                print(f"      Enable \"Settings > Storage > USB web interface\" on {RM_SSH_NAME}!")
                exit()
        else:
            # copy cached
            print("SKIP", file["path"])
            if DRY_RUN:
                return
            #pcpath_cached = RM_SSH_NAME + rmpath
            #shutil.copy2(pcpath_cached, pcpath)
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

    """
    # If a folder is trashed on RM, then its contents are NOT marked as trash
    # Thus, "redefine" a trashed file as a file that is in the trash or that has a parent in the trash
    def is_in_trash(fileid):
        print(files[fileid])
        if fileid == "": # root directory, is not in trash
            return False
        elif fileid
        elif fileid == "trash":
            return True
        else:
            return is_in_trash(files[fileid]["parent"])

    # Remove files whose parents
    for fileid in files:
        if is_in_trash(fileid):
            print("delete", files[fileid])
            del files[fileid]
    """

    # Build file tree edges
    for fileid, file in list(files.items()): # list copies keys and values, allowing deletion of dictionary entries in the loop
        if fileid == "":
            continue # skip root
        if file["parent"] not in files:
            del files[fileid] # e.g. forget files that are in a deleted folder
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
    uploaded_files = False
    for pc_path in pc_paths(skip_root=True, skip_hidden=True, top_down=False):
        is_dir = is_directory(pc_path)
        is_root = pc_path == RM_SSH_NAME

        rm_exists = pc_path in rm_files_by_pc_path
        rm_file = rm_files_by_pc_path[pc_path] if rm_exists else None
        pc_parent_path = None if is_root else os.path.dirname(pc_path)
        if pc_parent_path == RM_SSH_NAME:
            pc_parent_path += "/" # TODO: remove special case
        rm_parent_file = None if is_root or pc_parent_path not in rm_files_by_pc_path else rm_files_by_pc_path[pc_parent_path]
        rm_mtime = 0 if not rm_exists else int(rm_file["lastModified"])
        pc_mtime = int(os.path.getmtime(pc_path) * 1000)
        if rm_exists and pc_mtime > rm_mtime and not is_dir:
            rm_file = upload_file(pc_path, rm_file, rm_parent_file) # update
            uploaded_files = True
        elif not rm_exists:
            if not is_dir and os.path.getctime(pc_path) > os.path.getmtime(pc_path):
                os.utime(pc_path, (os.path.getatime(pc_path), os.path.getctime(pc_path))) # set mtime = ctime
            pc_mtime = int(os.path.getmtime(pc_path) * 1000)
            # TODO: check prev sync time, then delete or upload
            print((pc_mtime - last_sync) / 1000, "sec")
            print("PC mtime ", datetime.datetime.fromtimestamp(pc_mtime / 1000))
            print("Last sync", datetime.datetime.fromtimestamp(last_sync / 1000))
            if pc_mtime > last_sync and rm_parent_file: # delete if file does not have a parent
                rm_file = upload_file(pc_path, rm_file, rm_parent_file) # create
                uploaded_files = True
            else:
                delete_file_pc(pc_path, pc_parent_path)
        rm_files_by_pc_path[pc_path] = rm_file

    if uploaded_files:
        # Remarkable system needs to be reloaded to show uploaded files
        print("Restarting RM interface")
        rm_run("systemctl restart xochitl")

    if not DRY_RUN:
        write_last_sync_time()

    print("Complete")

def write_file(path, text):
    with open(f"/tmp/rmirro-{path}", "w") as file:
        file.write(text)
    pc_run(f"scp /tmp/rmirro-{path} {RM_SSH_NAME}:{RM_CONTENT_PATH}/{path}")

def write_content(id):
    pass # TODO: needed?

def write_metadata(id, metadata):
    write_file(f"{id}.metadata", json.dumps(metadata, indent=4))

def read_metadata(id):
    mdfile = open(f"{RM_SSH_NAME}_metadata/{id}.metadata", "r")
    return json.load(mdfile)

def is_directory(path):
    return path[-4:] not in [".pdf"]

def delete_file_pc(pc_path, pc_parent_path):
    print("RMPC", pc_path)
    if DRY_RUN:
        return

    atime = os.path.getatime(pc_parent_path)
    mtime = os.path.getmtime(pc_parent_path)

    if is_directory(pc_path):
        os.rmdir(pc_path)
    else:
        os.remove(pc_path)
        
    os.utime(pc_parent_path, (atime, mtime)) # restore old (atime, mtime), since we use mtime to determine how to sync files/directories

def upload_file(pc_path, rm_file, rm_parent_file):
    print("PUSH", pc_path)
    if DRY_RUN:
        return

    # TODO: NEVER overwrite a note on Remarkable with a PDF

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
        rm_file = read_metadata(id) # read original metadata, don't pollute with our own

    rm_file["lastModified"] = str(pc_mtime)
    rm_file["synced"] = False

    # send file
    write_file(f"{id}.metadata", json.dumps(rm_file, indent=4) + "\n")
    write_file(f"{id}.content", json.dumps({}, indent=4) + "\n")
    if rm_file["type"] == "DocumentType":
        print(f"scp \"{pc_path}\" {RM_SSH_NAME}:{RM_CONTENT_PATH}/{id}.pdf") # send file
        pc_run(f"scp \"{pc_path}\" {RM_SSH_NAME}:{RM_CONTENT_PATH}/{id}.pdf") # send file

    rm_file["id"] = id # add id, AFTER writing file
    return rm_file

if __name__ == "__main__":
    #create_file("/a/B/c.pdf", {"id": "cjfdks"})
    #upload_files(files)

    files = download_files()
