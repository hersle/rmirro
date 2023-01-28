#!/usr/bin/python3

import subprocess
import os
import json
import urllib.request
import uuid
import time
import argparse
import shutil

parser = argparse.ArgumentParser(
    prog = "rmirro",
    description = "Mirror PDFs of documents on a Remarkable, and upload documents to it, all from a native file system folder"
)
parser.add_argument("ssh-name", type=str, nargs="?", default="remarkable")
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--confirm", action="store_true")
# TODO: --favorites-only (or by tags)
# TODO: --pull-only, --push-only, etc.

def pc_run(cmd):
    output = subprocess.getoutput(cmd)
    return output

class Logger:
    def __init__(self):
        self.id = None

    def notify(self, text, urgency="normal", icon="input-tablet"):
        title = f"Synchronising reMarkable"
        cmd  = "notify-send"
        cmd += " --print-id"
        cmd += f" --replace-id={self.id}" if self.id else ""
        cmd += f" --app-name=rmirro --urgency={urgency} --icon={icon}"
        cmd += f" \"{title}\"" + f" \"{text}\""
        output = pc_run(cmd)
        self.id = int(output)

    def log(self, text, urgency="normal"):
        print(text)
        self.notify(text, urgency=urgency)

class Remarkable:
    def __init__(self, ssh_name):
        self.ssh_name = ssh_name

        self.raw_dir_remote = "/home/root/.local/share/remarkable/xochitl"
        self.processed_dir_local = f"{self.ssh_name}"
        self.raw_dir_local = os.path.abspath(self.processed_dir_local + "/.metadata")
        self.last_sync_path = self.processed_dir_local + "/.last_sync"

        # "ping" to check if we do indeed have a remarkable connected
        assert self.run("uname -n") == "reMarkable"

        self.ssh_ip = pc_run(f"ssh {self.ssh_name} -v exit 2>&1 | grep 'Connecting to' | cut -d' ' -f4") # e.g. 10.11.99.1
        logger.log(f"Connected to {self.ssh_name} ({self.ssh_ip})")

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
        if os.path.exists(self.raw_dir_local):
            shutil.rmtree(self.raw_dir_local)
        os.makedirs(self.raw_dir_local)
        pc_run(f"rsync -az {self.ssh_name}:{self.raw_dir_remote}/*.metadata {self.raw_dir_local}/") # TODO: figure out how to make rsync make exact mirror of dest dir, removing files in local dir. it screws up when using *.metadata wildcards and --delete

    def read_file(self, filename):
        with open(self.raw_dir_local + "/" + filename, "r") as file:
            return file.read()

    def read_json(self, filename):
        return json.loads(self.read_file(filename))

    def read_metadata(self, id):
        return self.read_json(f"{id}.metadata")

    def upload_file(self, src_path, dest_name):
        pc_run(f"scp \"{src_path}\" \"{self.ssh_name}:{self.raw_dir_remote}/{dest_name}\"") # TODO: avoid escaping " with proper list use of subprocess

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

    def run(self, cmd):
        return pc_run(f"ssh {self.ssh_name} {cmd}")

    def restart(self):
        print("Restarting remarkable interface")
        self.run("systemctl restart xochitl") # restart remarkable interface (to show any new files)

class AbstractFile:
    def list(self):
        for child in self.children(): # TODO: make use pythonic for ... in self:
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
        self.id = id
        if not self.trashed() and self.path() not in self.fullpath_to_id_cache:
            self.fullpath_to_id_cache[self.path()] = self.id # cache

    def metadata(self):
        return rm.read_metadata(self.id)

    def trashed(self):
        # TODO: if file is trashed, or its parent is trashed
        if self.id == "trash": # TODO: make is_trash() and is_root()
            return True
        if self.is_root:
            return False
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

        if self.is_file() and not path.endswith(".pdf"):
            path += ".pdf" # add extension (to notes) if TODO: .pdf only?

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
        # TODO: verify that it is equivalent to not is_directory()
        return not self.is_root and self.metadata()["type"] == "DocumentType"

    def last_modified(self):
        if self.is_root:
            return 0 # TODO: valid?
        return int(self.metadata()["lastModified"]) // 1000 # s

    def last_accessed(self):
        if self.is_root:
            return 0 # TODO: valid?
        return int(self.metadata()["lastOpened"]) // 1000 # s

    def download(self):
        path_local = rm.processed_dir_local + "/" + self.path()
        if self.is_directory():
            os.makedirs(path_local, exist_ok=True) # make directories ourselves
        else: # is file
            url = f"http://{rm.ssh_ip}/download/{self.id}/placeholder"
            urllib.request.urlretrieve(url, filename=path_local)
            atime = self.last_accessed() # s
            mtime = self.last_modified() # s
            os.utime(path_local, (atime, mtime)) # sync with access/modification times from RM

    def on_computer(self):
        pc_file = ComputerFile(rm.processed_dir_local).find(self.path())
        return pc_file if pc_file.exists() else None

class ComputerFile(AbstractFile):
    def __init__(self, path):
        self._path = path
        assert self.extension() in ("", ".pdf"), "can only handle directories and PDFs"

    def exists(self):
        return os.path.exists(self.path())

    def path(self):
        return self._path

    def name(self):
        filename = os.path.basename(self.path()) # e.g. "document.pdf"
        name, ext = os.path.splitext(filename) # e.g. ("document", ".pdf")
        assert ext in ["", ".pdf"], f"Unknown filetype: {ext}" # TODO: ?
        return name

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
        # TODO: don't create new RM root file
        return rm_root.find(self.path_on_remarkable())

    # TODO: can use RM web interface for uploading, if don't need to make new directories?
    def upload(self):
        # TODO: what to do if this is a *note* on the remarkable?
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
                metadata["lastOpened"] = str(self.last_accessed() * 1000) # only files have this property, # TODO: what to use here?

        metadata["lastModified"] = str(self.last_modified() * 1000)

        rm.write_metadata(id, metadata)
        rm.write_content(id, {}) # this file is required for RM to list file properly
        if metadata["type"] == "DocumentType":
            rm.upload_file(self.path(), f"{id}.pdf")

    def remove(self):
        if self.is_directory():
            os.rmdir(self.path())
        else:
            os.remove(self.path())

def sync_action_and_reason(rm_file, pc_file):
    if rm_file and not pc_file:
        return "PULL", "only on RM" # file does not exist on computer, so pull it (for safety, nothing is ever deleted from the remarkable, TODO: change?)

    if pc_file:
        if rm_file and rm_file.is_file(): # if the file is a directory, there is nothing worth updating
            diff = rm_file.last_modified() - pc_file.last_modified()
            if diff > 0:
                return "PULL", f"newer on RM"
            elif diff < 0:
                return "PUSH", f"newer on PC"
        elif not rm_file:
            # file/directory only on PC: was it removed from RM, or created on PC after last sync?
            # use creation time for directories and modification time for files, since directory modification time is dynamic
            #
            # Also, if a user moves a file to the PC directory, the original's modification time can be kept
            # In this case, we want to compare the creation time
            # This SHOULD NOT BE DONE if the file exists on the remarkable, because then downloaded files can be uploaded back!
            pc_time = pc_file.created() if pc_file.is_directory() or pc_file.created() > pc_file.last_modified() else pc_file.last_modified()
            diff = rm.last_sync() - pc_time
            if diff < 0:
                return "PUSH", f"added on PC"
            else:
                return "DROP", f"deleted on RM"

    return "SKIP", "up-to-date"

def sync(dry_run):
    def iterate_files():
        for rm_file in rm_root.traverse():
            pc_file = rm_file.on_computer()
            yield (rm_file, pc_file)
        for pc_file in pc_root.traverse():
            rm_file = pc_file.on_remarkable()
            if not rm_file: # already processed files on RM in last loop
                yield (rm_file, pc_file)

    commands = []
    for rm_file, pc_file in iterate_files():
        action, reason = sync_action_and_reason(rm_file, pc_file)
        if action != "SKIP":
            commands.append((action, reason, rm_file, pc_file))

    # sort commands, so that
    # * pushes happen first, then pulls, then drops
    # * push/pull handles shallow files first (creating directories as going down the tree),
    # * drop handles deep files first (deleting directories going up the tree, since non-empty directories should not be deleted)
    def key(command):
        action, reason, rm_file, pc_file = command
        key1 = ["PULL", "PUSH", "DROP"].index(action) # pull first, then push, then drop
        path = rm_file.path() if rm_file else pc_file.path_on_remarkable()
        key2 = -len(path) if action == "DROP" else +len(path)  # drop sub-files first (cannot remove non-empty directories)
        return (key1, key2)
    commands.sort(key=key)

    # print and perform commands
    rm_needs_restart = False
    for action, reason, rm_file, pc_file in commands:
        prefix = "DRY-" if dry_run else ""
        path = rm_file.path() if rm_file else pc_file.path_on_remarkable()
        logger.log(prefix + f"{action} ({reason}): {path}", notify=False)
        if not dry_run:
            if action == "PULL":
                rm_file.download()
            elif action == "PUSH":
                pc_file.upload()
            elif action == "DROP":
                pc_file.remove()
            rm_needs_restart = rm_needs_restart or action == "PUSH"

    if not dry_run:
        rm.write_last_sync()
        if rm_needs_restart:
            rm.restart()

    actions = [command[0] for command in commands]
    npull = actions.count("PULL") if not dry_run else 0
    npush = actions.count("PUSH") if not dry_run else 0
    ndrop = actions.count("DROP") if not dry_run else 0
    logger.log(f"Finished pulling {npull}, pushing {npush} and dropping {ndrop} files")

if __name__ == "__main__":
    args = parser.parse_args()
    assert not (getattr(args, "confirm") and getattr(args, "dry_run")), "ambiguous use of --confirm and --dry-run"

    ssh_name = getattr(args, "ssh-name")
    confirm = getattr(args, "confirm")
    dry_run = getattr(args, "dry_run") or confirm

    logger = Logger()
    rm = Remarkable(ssh_name) # TODO: avoid this global variable
    rm_root = RemarkableFile()
    pc_root = ComputerFile(rm.processed_dir_local)

    sync(dry_run)

    if confirm: # show user changes that will be made (in dry mode), then ask to proceed (in "wet mode")
        logger.log("Waiting for user confirmation")
        answer = input("Proceed with these operations (y/n)? ")
        if answer == "y":
            sync(False)
