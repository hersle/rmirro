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
parser.add_argument("-r", "--renderer", type=str, default="render_usb.py", metavar="ex", help="name of an executable in this project's directory such that \"ex infile outfile\" renders a reMarkable document with stem infile to the PDF outfile (default: render_usb.py - using the official USB web interface renderer)")
parser.add_argument("-v", "--verbose", action="store_true", help="print executed shell commands")
# TODO: --favorites-only (or by tags)
# TODO: --pull-only, --push-only, --backup, etc?
# TODO: let user exclude certain files? how would this pan out if they are suddenly included again?
# TODO: build symlink directory structure by tags?
# TODO: set --output directory
# TODO: support renderers that output e.g. SVG instead of PDF?

def panic(error):
    logger.log("ERROR: " + error)
    exit(1)

def pc_run(cmd, exiterror=None, verbose=None):
    verbose = getattr(args, "verbose") if verbose is None else False
    if verbose:
        print(">", subprocess.list2cmdline(cmd))
    proc = subprocess.run(cmd, capture_output=True, encoding="utf-8")
    if proc.returncode != 0 and exiterror is not None:
        print(proc.stderr)
        panic(exiterror)
    return proc.stdout

class Logger:
    def __init__(self):
        self.id = None

    def notify(self, text, urgency="normal", icon="input-tablet"):
        title = f"Synchronizing reMarkable"
        cmd  = ["notify-send"]
        cmd += ["--print-id"]
        cmd += [f"--replace-id={self.id}"] if self.id else []
        cmd += [f"--app-name=rmirro", f"--urgency={urgency}", f"--icon={icon}"]
        cmd += [title, text]
        output = pc_run(cmd, verbose=False)
        self.id = int(output)

    def log(self, text, urgency="normal", console=True, notification=True):
        if console:
            print(text)
        if notification:
            self.notify(text, urgency=urgency)

class Remarkable:
    def __init__(self, ssh_name):
        self.ssh_name = ssh_name

        self.raw_dir_remote = "/home/root/.local/share/remarkable/xochitl"
        self.processed_dir_local = os.path.abspath(f"{self.ssh_name}")
        self.raw_dir_local = os.path.abspath(f"{self.ssh_name}_metadata")
        self.backup_dir = os.path.abspath(f"{self.ssh_name}_backup")
        self.last_sync_path = self.processed_dir_local + "/.last_sync"

        # "ping" to check if we do indeed have a remarkable connected
        if self.run("uname -n", exiterror=f"Could not connect to {self.ssh_name} with SSH") != "reMarkable\n":
            panic(f"Could not verify that SSH host {self.ssh_name} is a reMarkable")

        logger.log(f"Connected to {self.ssh_name}")

        self.backup()
        self.download_metadata()

        # RM .metadata files store the parent of each file.
        # Manually, keep track of the children of every file, too,
        # since this is needed for traversing the RM directory tree downwards.
        self.children_cache = {"": [], "trash": []} # root and trash are "implicit", as they don't appear in filenames
        for id in self.ids():
            self.children_cache[id] = []
        for id in self.ids():
            metadata = self.read_metadata(id)
            self.children_cache[metadata["parent"]].append(id)

    def last_sync(self):
        if os.path.exists(self.last_sync_path):
            with open(self.last_sync_path, "r") as file:
                return int(file.read())
        return float("inf") # never synced before (i.e. infinitely far in the future)

    def write_last_sync(self):
        with open(self.last_sync_path, "w") as file:
            file.write(str(int(time.time())) + "\n") # s

    def ids(self):
        for filename in os.listdir(self.raw_dir_local):
            id, ext = os.path.splitext(filename)
            if ext == ".metadata":
                yield id

    def download_metadata(self):
        logger.log(f"Downloading metadata to {self.raw_dir_local}")

        # download/update local storage of .metadata files,
        # deleting any files on PC that are no longer on RM
        os.makedirs(self.raw_dir_local, exist_ok=True) # create directories if they do not exist
        pc_run(["rsync", "-az", "--delete-excluded", "--include=*.metadata", "--exclude=*", f"{self.ssh_name}:{self.raw_dir_remote}/", f"{self.raw_dir_local}/"], exiterror="Failed downloading metadata")

    def backup(self):
        logger.log(f"Backing up raw files to {self.backup_dir}")
        os.makedirs(self.backup_dir, exist_ok=True) # create directories if they do not exist
        pc_run(["rsync", "-az", "--delete", f"{self.ssh_name}:{self.raw_dir_remote}/", f"{self.backup_dir}/"], exiterror="Failed backing up raw files")

    def read_file(self, filename):
        with open(self.raw_dir_local + "/" + filename, "r") as file:
            return file.read()

    def read_json(self, filename):
        return json.loads(self.read_file(filename))

    def read_metadata(self, id):
        return self.read_json(f"{id}.metadata")

    def upload_file(self, src_path, dest_name):
        pc_run(["scp", src_path, f"{self.ssh_name}:{self.raw_dir_remote}/{dest_name}"])

    def write_file(self, filename, content):
        # write locally
        path_local = f"{self.raw_dir_local}/{filename}"
        with open(path_local, "w") as file:
            file.write(content)

        # copy same file to remarkable
        self.upload_file(path_local, filename)

    def write_json(self, filename, dict):
        self.write_file(filename, json.dumps(dict) + "\n")

    def write_metadata(self, id, metadata):
        self.write_json(f"{id}.metadata", metadata)
        self.children_cache[metadata["parent"]].append(id)

    def write_content(self, id, content):
        self.write_json(f"{id}.content", content)

    def run(self, cmd, exiterror=None):
        return pc_run(["ssh", "-o", "ConnectTimeout=1", self.ssh_name, cmd], exiterror=exiterror)

    def restart(self):
        print("Restarting remarkable interface")
        self.run("systemctl restart xochitl") # restart remarkable interface (to show any new files)

class AbstractFile:
    def list(self):
        for child in self.children():
            print(child.path())
            child.list()

    def traverse(self):
        for child in self.children():
            if child.name()[0] == ".":
                continue # skip hidden files
            else:
                yield child
                yield from child.traverse()

class RemarkableFile(AbstractFile):
    fullpath_to_id_cache = {} # build as we go

    def __init__(self, id=""):
        self.is_root = id == ""
        self.is_trash = id == "trash"
        self.id = id
        if not self.trashed() and self.path() not in self.fullpath_to_id_cache:
            self.fullpath_to_id_cache[self.path()] = self.id # cache

        # verify this is a file XOR a directory (to make sure our logic is consistent)
        assert self.is_file() != self.is_directory(), f"reMarkable file \"{self.id}\" is not a file XOR a directory"

    def metadata(self):
        return rm.read_metadata(self.id)

    def trashed(self):
        if self.is_trash:
            return True
        if self.is_root:
            return False
        # On RM, a file can be marked as trashed even though its parent is not
        # Override this, so that a file is trashed if its parent is
        return self.parent().trashed()

    def children(self):
        for id in rm.children_cache[self.id]:
            yield RemarkableFile(id)

    def parent(self):
        if "parent" in self.metadata():
            parent_id = self.metadata()["parent"]
            return RemarkableFile(parent_id)
        else:
            return None # e.g. for root and trash

    def name(self):
        if self.is_root:
            return ""
        return self.metadata()["visibleName"]

    def path(self):
        if self.is_root:
            path = ""
        elif self.parent().is_root:
            path = self.name()
        else:
            path = self.parent().path() + "/" + self.name()

        # Files with no extension: RM notes (to be regarded as PDFs after export)
        # Files with .pdf extension: (annotated) PDFs
        # Files with .epub extension: (annotated) EPUBs
        if self.is_file() and not (path.endswith(".pdf") or path.endswith(".epub")):
            path += ".pdf" # add PDF extension to to-be-exported notes

        return path

    def find(self, path):
        if path == "":
            return self
        if not self.is_root:
            path = self.path() + "/" + path # relative -> full path
        if path in self.fullpath_to_id_cache:
            return RemarkableFile(self.fullpath_to_id_cache[path]) # cache
        for file in self.traverse():
            if file.path() == path:
                return file
        return None

    def is_directory(self):
        return self.is_root or self.metadata()["type"] == "CollectionType"

    def is_file(self):
        return not self.is_root and self.metadata()["type"] == "DocumentType"

    def last_modified(self):
        return 0 if self.is_root else int(self.metadata()["lastModified"]) // 1000 # s

    def last_accessed(self):
        return 0 if self.is_root else int(self.metadata()["lastOpened"]) // 1000 # s

    def download(self):
        infile  = rm.backup_dir + "/" + self.id
        outfile = rm.processed_dir_local + "/" + self.path()
        if self.is_directory():
            os.makedirs(outfile, exist_ok=True) # make directories ourselves
        else: # is file
            pc_run([f"{DIR}/{renderer}", infile, outfile], exiterror=f"Failed to render {self.path()}")

            # double-check that file was downloaded
            if not os.path.exists(outfile):
                panic(f"Failed to render {self.path()}")

            # copy last access/modification time from RM to PC file system
            atime = self.last_accessed() # s
            mtime = self.last_modified() # s
            os.utime(outfile, (atime, mtime)) # sync with access/modification times from RM

    def on_computer(self):
        pc_file = ComputerFile(rm.processed_dir_local).find(self.path())
        return pc_file if pc_file.exists() else None

class ComputerFile(AbstractFile):
    def __init__(self, path):
        self._path = path

    def exists(self):
        return os.path.exists(self.path())

    def path(self):
        return self._path

    def name(self):
        filename = os.path.basename(self.path()) # e.g. "document.pdf"
        name, ext = os.path.splitext(filename) # e.g. ("document", ".pdf")
        return name # without extension

    def extension(self):
        _, ext = os.path.splitext(self.path())
        return ext

    def parent(self):
        return ComputerFile(os.path.dirname(self.path()))

    def is_directory(self):
        return os.path.isdir(self.path())

    def is_file(self):
        return os.path.isfile(self.path())

    def children(self):
        if self.is_directory():
            return [ComputerFile(self.path() + "/" + name) for name in os.listdir(self.path())]
        else:
            return []

    def find(self, name):
        return ComputerFile(self.path() + "/" + name)

    def created(self):
        return int(os.path.getctime(self.path())) # s

    def last_accessed(self):
        return int(os.path.getatime(self.path())) # s

    def last_modified(self):
        return int(os.path.getmtime(self.path())) # s

    def path_on_remarkable(self):
        rm_path = os.path.relpath(self.path(), start=rm.processed_dir_local)
        if rm_path == ".":
            rm_path = ""
        return rm_path

    def on_remarkable(self):
        return rm_root.find(self.path_on_remarkable())

    # TODO: can use RM web interface for uploading, if don't need to make new directories?
    # then it would not be necessary to restart the RM interface
    def upload(self):
        if self.is_file() and self.extension() not in (".pdf", ".epub"):
            panic(f"Extension of {self.path()} is not PDF or EPUB")

        rm_file = self.on_remarkable()

        if rm_file:
            id = rm_file.id
            metadata = rm_file.metadata()
        else:
            assert self.parent().on_remarkable(), "cannot upload file whose parent does not exist!"
            id = uuid.uuid4() # create new
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
                metadata["lastOpened"] = str(self.last_accessed() * 1000) # only files have this property

        metadata["lastModified"] = str(self.last_modified() * 1000)

        rm.write_metadata(id, metadata)
        rm.write_content(id, {}) # this file is required for RM to list file properly
        if metadata["type"] == "DocumentType":
            rm.upload_file(self.path(), f"{id}{self.extension()}")

    def remove(self):
        if self.is_directory():
            os.rmdir(self.path())
        else:
            os.remove(self.path())

def sync_action_and_reason(rm_file, pc_file):
    if rm_file and not pc_file:
        return "PULL", "only on RM" # file does not exist on computer, so pull it (for safety, nothing is ever deleted from the remarkable)

    if pc_file:
        if rm_file and rm_file.is_file(): # if the file is a directory, there is nothing worth updating
            if rm_file.last_modified() > pc_file.last_modified():
                return "PULL", f"newer on RM"
            elif rm_file.last_modified() < pc_file.last_modified():
                return "PUSH", f"newer on PC"
        elif not rm_file:
            # file/directory only on PC: was it removed from RM, or created on PC after last sync?
            # use creation time for directories and modification time for files, since directory modification time is dynamic
            #
            # Also, if a user moves a file to the PC directory, the original's modification time can be kept
            # In this case, we want to compare the creation time
            # This SHOULD NOT BE DONE if the file exists on the remarkable, because then downloaded files can be uploaded back!
            pc_time = pc_file.created() if pc_file.is_directory() or pc_file.created() > pc_file.last_modified() else pc_file.last_modified()
            if rm.last_sync() < pc_time:
                return "PUSH", f"added on PC"
            else:
                return "DROP", f"deleted on RM"

    return "SKIP", "up-to-date"

if __name__ == "__main__":
    args = parser.parse_args()
    ssh_name = getattr(args, "name")
    renderer = getattr(args, "renderer")

    logger = Logger()

    rm = Remarkable(ssh_name)
    rm_root = RemarkableFile()
    pc_root = ComputerFile(rm.processed_dir_local)

    def iterate_files():
        for rm_file in rm_root.traverse():
            pc_file = rm_file.on_computer()
            yield (rm_file, pc_file)
        for pc_file in pc_root.traverse():
            rm_file = pc_file.on_remarkable()
            if not rm_file: # already processed files on RM in last loop
                yield (rm_file, pc_file)

    print(f"Synchronizing PDFs with {rm.processed_dir_local}")

    logger.log("Comparing files and collecting commands")
    commands = {"PULL": [], "PUSH": [], "DROP": []}
    for rm_file, pc_file in iterate_files():
        action, reason = sync_action_and_reason(rm_file, pc_file)
        path = rm_file.path() if rm_file else pc_file.path_on_remarkable()
        if action != "SKIP":
            commands[action].append((action, reason, path, rm_file, pc_file))

    # sort commands
    def key(command):
        action, reason, path, rm_file, pc_file = command
        return path
    commands["PULL"].sort(key=key, reverse=False) # pull shallow files first (creating directories before pulling their contents)
    commands["PUSH"].sort(key=key, reverse=False) # push shallow files first (creating directories before pushing their contents)
    commands["DROP"].sort(key=key, reverse=True)  # drop deep files first (deleting directories' contents before themselves)
    commands = commands["PULL"] + commands["PUSH"] + commands["DROP"] # join all commands in one list (pull first, then push, then drop)

    # list commands and prompt for proceeding
    actions = [command[0] for command in commands]
    npull = actions.count("PULL")
    npush = actions.count("PUSH")
    ndrop = actions.count("DROP")
    for i, (action, reason, path, rm_file, pc_file) in enumerate(commands):
        print(f"? ({i+1}/{len(commands)}) {action}: {path}")

    if len(commands) == 0:
        logger.log("Finished (everything was up-to-date)")
        exit()
    else:
        logger.log(f"Pull {npull}, push {npush} and drop {ndrop} files, rendering with {renderer}?", console=False) # print in console on next line
        answer = input(f"Pull {npull}, push {npush} and drop {ndrop} files, rendering with {renderer} (y/n)? ")
        if answer != "y": # accept nothing but a resounding yes
            logger.log("Aborted (no changes have been made)")
            exit()

    # execute commands
    rm_needs_restart = False
    for i, (action, reason, path, rm_file, pc_file) in enumerate(commands):
        logger.log(f"! ({i+1}/{len(commands)}) {action}: {path}")
        if action == "PULL":
            rm_file.download()
        elif action == "PUSH":
            pc_file.upload()
        elif action == "DROP":
            pc_file.remove()
        rm_needs_restart = rm_needs_restart or action == "PUSH"

    rm.write_last_sync()
    if rm_needs_restart:
        rm.restart()

    logger.log(f"Finished (pulled {npull}, pushed {npush} and dropped {ndrop} files)")
