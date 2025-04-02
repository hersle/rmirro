#!/usr/bin/python3

import subprocess
import os
import json
import urllib.request
import uuid
import time
import argparse
import shutil

# directory of this file
# (e.g. /some/absolute/path/rmirro)
DIR = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser(
    prog = "rmirro",
    description = "Synchronize reMarkable with local directory \"[name]/\"",
)
parser.add_argument("name", type=str, nargs="?", default="remarkable", help="SSH hostname of reMarkable reachable with \"ssh [name]\" without password (default: remarkable)")
parser.add_argument("-r", "--renderers", default=["render_usb.py"], nargs="+", metavar="EX", help="list of one or more executables EX in this project's directory such that \"EX infile outfile\" renders a reMarkable document with stem infile to the PDF outfile (default: render_usb.py - using the official USB web interface renderer)")
parser.add_argument("-v", "--verbose", action="store_true", help="print executed shell commands")
parser.add_argument("-s", "--skip", default=["Quick sheets"], nargs="*", help="skip file names (default: skip \"Quick sheets\"; pass empty -s to include)")

# TODO: --favorites-only (or by tags)
# TODO: --pull-only, --push-only, --backup, etc?
# TODO: let user exclude certain files? how would this pan out if they are suddenly included again?
# TODO: build symlink directory structure by tags?
# TODO: set --output directory
# TODO: support renderers that output e.g. SVG instead of PDF?

# Print an error message and exit
def panic(error):
    print("ERROR: " + error)
    exit(1) # nonzero status code marks failure

# Run a shell command on the local computer,
# Optionally panic with exiterror if it fails
# Optionally capture and return its output
def pc_run(cmd, exiterror=None, capture=True):
    if args.verbose:
        print(">", subprocess.list2cmdline(cmd)) # print the command

    proc = subprocess.run(cmd, capture_output=capture, encoding="utf-8")
    if proc.returncode != 0 and exiterror is not None:
        print(proc.stderr, end="")
        panic(exiterror)

    return proc

# Interface to communicate with reMarkable and operate on its raw file system
class Remarkable:
    def __init__(self, ssh_name):
        self.ssh_name = ssh_name # e.g. "remarkable"

        self.raw_dir_remote = "/home/root/.local/share/remarkable/xochitl" # path to raw notes on RM
        self.processed_dir_local = os.path.abspath(f"{self.ssh_name}") # path to rendered PDFs on PC (e.g. remarkable/)
        self.raw_dir_local = os.path.abspath(f"{self.ssh_name}_metadata") # path to *.metadata files on PC (downloaded from RM) (e.g. remarkable_metadata/)
        self.backup_dir = os.path.abspath(f"{self.ssh_name}_backup") # path to save a backup of all raw RM files on PC (e.g. remarkable_backup/)
        self.last_sync_path = self.processed_dir_local + "/.last_sync" # path to a file on PC with the timestamp at which the last sync was performed

        # create directories if they do not exist
        os.makedirs(self.processed_dir_local, exist_ok=True)
        os.makedirs(self.raw_dir_local, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        # "ping" to check if we do indeed have a remarkable connected
        print(f"Connecting to {self.ssh_name}")
        if self.run("uname -n", exiterror=f"Could not connect to {self.ssh_name} with SSH").stdout not in ("reMarkable\n", "imx8mm-ferrari\n"): # covers (RM1, RM2) and (RMPP)
            panic(f"Could not verify that SSH host {self.ssh_name} is a reMarkable")
        print(f"Connected to {self.ssh_name}")

        self.backup()
        self.download_metadata()

        # RM .metadata files store only the *parent* of each file
        # keep track of every file's *children* too,
        # to effectively traverse its file tree later
        self.children_cache = {"": [], "trash": []} # root and trash are "implicit/special", as they don't appear in filenames
        for id in self.ids():
            self.children_cache[id] = [] # initialize list for each file
        for id in self.ids():
            metadata = self.read_metadata(id)
            if args.verbose:
                print(f"Read {id = } with {metadata = }")
            parent_id = metadata["parent"]
            self.children_cache[parent_id].append(id)

    # Read the timestamp at which the last sync was performed
    def last_sync(self):
        if os.path.exists(self.last_sync_path):
            with open(self.last_sync_path, "r") as file:
                return int(file.read()) # s
        return float("inf") # never synced before (i.e. infinitely far in the future)

    # Write the timestamp at which the last sync was performed (by default, now)
    def write_last_sync(self, t=int(time.time())):
        with open(self.last_sync_path, "w") as file:
            file.write(str(t) + "\n") # s

    # Generate IDs of all RM files
    def ids(self):
        for filename in os.listdir(self.raw_dir_local):
            id, ext = os.path.splitext(filename)
            if ext == ".metadata":
                yield id

    # Download all raw *.metadata files from RM with rsync
    def download_metadata(self):
        print(f"Downloading metadata to {self.raw_dir_local}")
        pc_run(["rsync", "--info=progress2", "-az", "--delete-excluded", "--include=*.metadata", "--exclude=*", f"{self.ssh_name}:{self.raw_dir_remote}/", f"{self.raw_dir_local}/"], exiterror="Failed downloading metadata", capture=False) # --delete-excluded deletes files on PC that are no longer on RM

    # Download all raw files from RM with rsync
    def backup(self):
        print(f"Backing up raw files to {self.backup_dir}")
        pc_run(["rsync", "--info=progress2", "-az", "--delete", f"{self.ssh_name}:{self.raw_dir_remote}/", f"{self.backup_dir}/"], exiterror="Failed backing up raw files", capture=False) # --delete deletes files on PC that are no longer on RM

    # Read a RM file that has been downloaded to PC
    def read_file(self, filename):
        with open(self.raw_dir_local + "/" + filename, "r") as file:
            return file.read()

    # Read a RM JSON file that has been downloaded to PC
    def read_json(self, filename):
        return json.loads(self.read_file(filename))

    # Read a RM .metadata file that has been downloaded to PC
    def read_metadata(self, id):
        return self.read_json(f"{id}.metadata")

    # Upload a file from the PC storage to RM
    def upload_file(self, src_path, dest_name): # TODO: use same prefix as read methods
        pc_run(["scp", src_path, f"{self.ssh_name}:{self.raw_dir_remote}/{dest_name}"])

    # Create a file in the PC storage and upload it to RM
    def write_file(self, filename, content):
        # write locally
        path_local = f"{self.raw_dir_local}/{filename}"
        with open(path_local, "w") as file:
            file.write(content)

        # copy same file to remarkable
        self.upload_file(path_local, filename)

    # Create a JSON file in the PC storage and upload it to RM
    def write_json(self, filename, dict):
        self.write_file(filename, json.dumps(dict) + "\n")

    # Create a .metadata file in the PC storage and upload it to RM
    def write_metadata(self, id, metadata):
        self.write_json(f"{id}.metadata", metadata)

        # update cache (parent -> child)
        if id not in self.children_cache[metadata["parent"]]:
            self.children_cache[metadata["parent"]].append(id)

        # update cache (child -> nothing)
        if id not in self.children_cache:
            self.children_cache[id] = []

    # Create a .content file in the PC storage and upload it to RM
    def write_content(self, id, content):
        self.write_json(f"{id}.content", content)

    # Run a shell command on RM
    def run(self, cmd, exiterror=None):
        return pc_run(["ssh", "-o", "ConnectTimeout=1", self.ssh_name, cmd], exiterror=exiterror)

    # Restart reMarkable's interface
    # (needed to show newly uploaded files)
    def restart(self):
        print("Restarting remarkable interface")
        self.run("systemctl restart xochitl")

# Some methods that are common to RM files and PC files
class AbstractFile:
    # List children of this file (like listing a directory)
    def list(self):
        for child in self.children():
            print(child.path())
            child.list()

    # Generate all descendants (children, children's children, ...) of this file
    def traverse(self):
        for child in self.children():
            if child.name()[0] == ".":
                continue # skip hidden files
            else:
                yield child # child
                yield from child.traverse() # child's children

# Represents a file stored on the reMarkable
class RemarkableFile(AbstractFile):
    # Cached lookup of RM file IDs by their full paths (common to all instances)
    fullpath_to_id_cache = {} # build as we go

    # Construct a RM file from its ID
    def __init__(self, id=""):
        self.is_root = id == ""
        self.is_trash = id == "trash"
        self.id = id

        if not self.trashed() and self.path() not in self.fullpath_to_id_cache:
            self.fullpath_to_id_cache[self.path()] = self.id # cache

        # Verify this is a file XOR a directory, to make sure our logic is consistent
        assert self.is_file() != self.is_directory(), f"reMarkable file \"{self.id}\" is not a file XOR a directory"

    # Read and return metadata attributes as a dictionary
    def metadata(self):
        return rm.read_metadata(self.id)

    # Return whether this file is trashed
    def trashed(self):
        if self.is_trash:
            return True
        if self.is_root:
            return False
        # On RM, a file can be marked as trashed even though its parent is not
        # What on earth should be done, then, to a non-trashed that is in a trashed directory?
        # Here, it is more sensible to say that a file is trashed if its parent is trashed
        return self.parent().trashed()

    # Generate this file's children
    def children(self):
        for id in rm.children_cache[self.id]: # use cached parent-to-child lookup
            yield RemarkableFile(id)

    # Return this file's parent (directory), or None if it 
    def parent(self):
        if "parent" in self.metadata():
            parent_id = self.metadata()["parent"]
            return RemarkableFile(parent_id)
        else:
            assert self.is_root or self.is_trash, "file is an orphan"
            return None

    # Return this file's name (e.g. "document")
    def name(self):
        if self.is_root:
            return ""
        return self.metadata()["visibleName"]

    # Return this file's full path as it appears in the visual RM file system (e.g. notes/document.pdf)
    def path(self):
        if self.is_root:
            path = ""
        elif self.parent().is_root:
            path = self.name() # handle separately to get "toplevelfile" instead of "/toplevelfile"
        else:
            path = self.parent().path() + "/" + self.name()

        # Any file (note, annotated PDF or EPUB) will be a PDF upon export
        if self.is_file() and not (path.endswith(".pdf") or path.endswith(".epub")):
            path += ".pdf" # add PDF extension to to-be-exported notes

        return path

    # Find a descendant of this file by its relative path to it
    def find(self, path):
        if path == "":
            return self
        if not self.is_root:
            path = self.path() + "/" + path # relative to full path
        if path in self.fullpath_to_id_cache:
            return RemarkableFile(self.fullpath_to_id_cache[path]) # use cache
        for file in self.traverse():
            if file.path() == path:
                return file
        return None

    # Returns whether this "file" is a directory
    def is_directory(self):
        return self.is_root or self.metadata()["type"] == "CollectionType"

    # Returns whether this "file" is a file (i.e. document)
    def is_file(self):
        return not self.is_root and self.metadata()["type"] == "DocumentType"

    # Returns timestamp at which file was last modified
    def last_modified(self):
        return 0 if self.is_root else int(self.metadata()["lastModified"]) // 1000 # s

    # Returns timestamp at which file was last accessed (opened)
    def last_accessed(self):
        if self.is_root:
            return 0
        if "lastOpened" in self.metadata():
            return int(self.metadata()["lastOpened"]) // 1000 # s
        return self.last_modified()

    # Download this file to its corresponding location in the PC directory
    def download(self):
        infile  = rm.backup_dir + "/" + self.id # already have raw file(s) from the backup
        outfile = rm.processed_dir_local + "/" + self.path() # output folder/PDF location
        if self.is_directory():
            os.makedirs(outfile, exist_ok=True) # make directories ourselves
        else: # is file
            success = False
            for renderer in renderers:
                proc = pc_run([f"{DIR}/{renderer}", infile, outfile]) # try to render
                success = proc.returncode == 0
                if len(renderers) > 1 or args.verbose:
                    print(f"- {renderer}", "succeeded" if success else "failed")
                print(proc.stderr, end="")
                if success:
                    break # jump out upon first successful render

            # Double check that file was indeed downloaded
            success = success and os.path.exists(outfile)

            if not success:
                panic(f"All renderers failed to render {self.path()}")

            # Copy last access/modification time from RM to PC file system
            # (these are used to determine sync actions)
            atime = self.last_accessed() # s
            mtime = self.last_modified() # s
            os.utime(outfile, (atime, mtime))

    # Returns the corresponding file on PC, or None if it does not exist
    def on_computer(self):
        pc_file = ComputerFile(rm.processed_dir_local).find(self.path())
        return pc_file if pc_file.exists() else None

# Represents a file stored on the computer
class ComputerFile(AbstractFile):
    # Construct a PC file by its path
    def __init__(self, path):
        self._path = path

    # Returns whether the PC file exists
    def exists(self):
        return os.path.exists(self.path())

    # Returns the file's path
    def path(self):
        return self._path

    # Returns the file's filename without its extension
    def name(self):
        filename = os.path.basename(self.path()) # e.g. "document.pdf"
        name, ext = os.path.splitext(filename) # e.g. ("document", ".pdf")
        return name # without extension

    # Returns the file's extension
    def extension(self):
        _, ext = os.path.splitext(self.path())
        return ext

    # Returns the file's parent
    def parent(self):
        return ComputerFile(os.path.dirname(self.path()))

    # Returns whether the file is a directory
    def is_directory(self):
        return os.path.isdir(self.path())

    # Returns whether the "file" is a file (i.e. a document, i.e. not a directory)
    def is_file(self):
        return os.path.isfile(self.path())

    # Returns the file's children, if any
    def children(self):
        if self.is_directory():
            return [ComputerFile(self.path() + "/" + name) for name in os.listdir(self.path())]
        else:
            return []

    # Returns a descendant of this file by its path relative to it
    def find(self, name):
        return ComputerFile(self.path() + "/" + name)

    # Returns the timestamp at which the file was created
    def created(self):
        return int(os.path.getctime(self.path())) # s

    # Returns the timestamp at which the file was last accessed
    def last_accessed(self):
        return int(os.path.getatime(self.path())) # s

    # Returns the timestamp at which the file was last modified
    def last_modified(self):
        return int(os.path.getmtime(self.path())) # s

    # Returns the path that the PC file would have on RM
    def path_on_remarkable(self):
        rm_path = os.path.relpath(self.path(), start=rm.processed_dir_local) # path relative to base directory
        if rm_path == ".":
            rm_path = "" # RM root
        return rm_path

    # Returns the corresponding file on RM, or None if it does not exist
    def on_remarkable(self):
        return rm_root.find(self.path_on_remarkable())

    # Upload this PC file to RM
    # TODO: could use RM web interface for uploading, if don't need to make new directories?
    # TODO: then it would not be necessary to restart the RM interface
    def upload(self):
        if self.is_file() and self.extension() not in (".pdf", ".epub"):
            panic(f"Extension of {self.path()} is not PDF or EPUB")

        rm_file = self.on_remarkable()

        if rm_file:
            # RM file already exists, so we will only update it
            id = rm_file.id
            metadata = rm_file.metadata()
        else:
            # RM file does not exist, so we have to create it from scratch
            assert self.parent().on_remarkable(), "cannot upload file whose parent does not exist!"
            id = str(uuid.uuid4()) # create new ID
            assert id not in rm.ids(), f"{id} already exists on {rm.ssh_name}"
            metadata = {
                "visibleName": self.name(),
                "parent": self.parent().on_remarkable().id,
                "modified": False, # TODO: do I really need to set all these?
                "metadatamodified": False,
                "deleted": False,
                "pinned": False,
                "version": 0,
            }
            if self.is_directory():
                metadata["type"] = "CollectionType"
            else: # is file
                metadata["type"] = "DocumentType"
                metadata["lastOpened"] = str(self.last_accessed() * 1000) # s to ms, only files have this property

        metadata["lastModified"] = str(self.last_modified() * 1000) # s to ms

        rm.write_metadata(id, metadata)
        rm.write_content(id, {}) # this file is required for RM to list file properly
        if metadata["type"] == "DocumentType":
            rm.upload_file(self.path(), f"{id}{self.extension()}") # upload e.g. document.pdf in the "raw" form {id}.pdf

    # Remove (delete) this file on PC
    def remove(self):
        if self.is_directory():
            os.rmdir(self.path())
        else:
            os.remove(self.path())

# Determine what to do, and why, when syncing file with given RM/PC representations
def sync_action_and_reason(rm_file, pc_file, skip=[]):
    if (rm_file and rm_file.name() in skip) or (pc_file and pc_file.name() in skip):
        return "SKIP", "in --skip"

    if rm_file and not pc_file:
        return "PULL", "only on RM"

    elif rm_file and pc_file and rm_file.is_file(): # if the file is a directory, there is nothing worth updating (its name doesn't change)
        if rm_file.last_modified() > pc_file.last_modified():
            return "PULL", "newer on RM"
        elif rm_file.last_modified() < pc_file.last_modified():
            return "PUSH", "newer on PC"

    elif not rm_file and pc_file:
        # Was the file removed from RM or created on PC after last sync?
        # Compare last sync time to PC time to find out

        if pc_file.is_directory():
            # Directory modification times are changed every time its contents changes,
            # but the creation time stays constant, so go by this instead
            pc_time = pc_file.created()
        elif pc_file.created() > pc_file.last_modified():
            # When a file is copied from on PC, many programs preserve its
            # (old) modification time, so rather go by the (new) creation time
            # (only holds if the file does not exist on RM)
            pc_time = pc_file.created()
        else:
            # The default is that we want the time the file was modified last
            pc_time = pc_file.last_modified()

        if rm.last_sync() < pc_time:
            return "PUSH", "added on PC"
        else:
            return "DROP", "deleted on RM"

    return "SKIP", "up-to-date"

if __name__ == "__main__":
    args = parser.parse_args()
    ssh_name = getattr(args, "name")
    renderers = getattr(args, "renderers")
    skip = getattr(args, "skip")

    rm = Remarkable(ssh_name)
    rm_root = RemarkableFile()
    pc_root = ComputerFile(rm.processed_dir_local)

    # Iterate over all unique (RM file, PC file) pairs exactly once
    def iterate_files():
        for rm_file in rm_root.traverse():
            pc_file = rm_file.on_computer()
            yield (rm_file, pc_file)
        for pc_file in pc_root.traverse():
            rm_file = pc_file.on_remarkable()
            if not rm_file: # already processed files on RM in last loop
                yield (rm_file, pc_file)

    print(f"Synchronizing PDFs with {rm.processed_dir_local}")
    print("Will use renderer(s)", " -> ".join(renderers))

    print("Comparing files and collecting commands")
    commands = {"PULL": [], "PUSH": [], "DROP": []}
    for rm_file, pc_file in iterate_files():
        action, reason = sync_action_and_reason(rm_file, pc_file, skip=skip)
        path = rm_file.path() if rm_file else pc_file.path_on_remarkable()
        if action != "SKIP":
            commands[action].append((action, reason, path, rm_file, pc_file))
        elif reason != "up-to-date":
            print(f"SKIP {path}" + (f" ({reason})" if args.verbose else ""))

    # Sort commands
    def key(command):
        action, reason, path, rm_file, pc_file = command
        return path
    commands["PULL"].sort(key=key, reverse=False) # pull shallow files first (creating directories before pulling their contents)
    commands["PUSH"].sort(key=key, reverse=False) # push shallow files first (creating directories before pushing their contents)
    commands["DROP"].sort(key=key, reverse=True)  # drop deep files first (deleting directories' contents before themselves)
    commands = commands["PULL"] + commands["PUSH"] + commands["DROP"] # join all commands in one list (pull first, then push, then drop)

    # List commands and prompt before proceeding
    actions = [command[0] for command in commands]
    npull = actions.count("PULL")
    npush = actions.count("PUSH")
    ndrop = actions.count("DROP")
    for i, (action, reason, path, rm_file, pc_file) in enumerate(commands):
        print(f"? ({i+1}/{len(commands)}) {action}: {path}" + (f" ({reason})" if args.verbose else ""))

    if len(commands) == 0:
        print("Did nothing (everything was up-to-date)")
        exit()
    else:
        answer = input(f"Pull {npull}, push {npush} and drop {ndrop} files (y/n)? ")
        if answer != "y": # accept nothing but a resounding yes
            print("Aborted (no changes have been made)")
            exit()
        print(f"Pulling {npull}, pushing {npush} and dropping {ndrop} files")

    # Execute commands
    for i, (action, reason, path, rm_file, pc_file) in enumerate(commands):
        print(f"! ({i+1}/{len(commands)}) {action}: {path}")
        if action == "PULL":
            rm_file.download()
        elif action == "PUSH":
            pc_file.upload()
        elif action == "DROP":
            pc_file.remove()

    rm.write_last_sync()

    # RM interface must be restarted to show newly added files
    if npush > 0:
        rm.restart()

    print(f"Pulled {npull}, pushed {npush} and dropped {ndrop} files")
