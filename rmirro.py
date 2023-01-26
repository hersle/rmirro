#!/usr/bin/python3

import subprocess
import os
import json
import urllib.request
import uuid
import time
import argparse

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

# TODO: optimize!!! less file access
# TODO: what about using DP in RemarkableFile?
class Remarkable:
    def __init__(self, ssh_name):
        self.ssh_name = ssh_name

        self.raw_dir_remote = "/home/root/.local/share/remarkable/xochitl"
        self.processed_dir_local = f"{self.ssh_name}"
        self.raw_dir_local = os.path.abspath(self.processed_dir_local + ".metadata")
        self.last_sync_path = self.processed_dir_local + "/.last_sync"

        # "ping" to check if we do indeed have a remarkable connected
        assert self.run("uname -n") == "reMarkable"

        self.ssh_ip = pc_run(f"ssh {self.ssh_name} -v exit 2>&1 | grep 'Connecting to' | cut -d' ' -f4") # e.g. 10.11.99.1
        print(f"Connected to {self.ssh_name} ({self.ssh_ip})")

    def last_sync(self):
        if os.path.exists(self.last_sync_path):
            with open(self.last_sync_path, "r") as file:
                return int(file.read())
        return float("inf") # never synced before (i.e. infinitely far in the future)

    def write_last_sync(self):
        with open(self.last_sync_path, "w") as file:
            file.write(str(int(time.time())) + "\n") # s

    def download_metadata(self):
        pc_run(f"rsync -avzd {self.ssh_name}:{self.raw_dir_remote}/*.metadata {self.raw_dir_local}/")
        # TODO: remove files that are in RM trash!

    def read_file(self, path, tmpdest="/tmp/rmirro_tmp_file"):
        pc_run(f"scp {self.ssh_name}:{self.raw_dir_remote}/{path} {tmpdest}")
        with open(tmpdest, "r") as file:
            return file.read()

    def upload_file(self, src_path, dest_name):
        pc_run(f"scp {src_path} {self.ssh_name}:{self.raw_dir_remote}/{dest_name}")

    def write_file(self, filename, content):
        # write locally
        path_local = f"{self.raw_dir_local}/{filename}"
        with open(path_local, "w") as file:
            file.write(content)

        # copy same file to remarkable
        self.upload_file(path_local, filename)

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

    def traverse(self, depth_first=False):
        for child in self.children():
            if child.name()[0] == ".":
                continue # skip hidden files
            if depth_first:
                yield from child.traverse()
                yield child
            else: # breadth first
                yield child
                yield from child.traverse()

class RemarkableFile(AbstractFile):
    def __init__(self, id=""):
        self.is_root = id == ""
        self.id = id

    # TODO: file size?

    # TODO: make faster
    def metadata(self):
        # from local storage
        with open(rm.raw_dir_local + "/" + self.id + ".metadata", "r") as file:
            metadata = json.loads(file.read())
        return metadata

        # over ssh, very slow
        #return json.loads(rm.read_file(f"{self.id}.metadata"))

    def children(self):
        children = []
        for filename in os.listdir(rm.raw_dir_local):
            if filename.endswith(".metadata"):
                id = filename.removesuffix(".metadata")
                file = RemarkableFile(id)
                if file.parent().id == self.id:
                    children.append(file)
        return children

    def parent(self):
        if self.is_root:
            return None
        parent_id = self.metadata()["parent"]
        assert parent_id is not None
        return RemarkableFile(parent_id)

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
        return RemarkableFile().find(self.path_on_remarkable())

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

        # TODO: upload this and PDF!
        rm.write_file(f"{id}.metadata", json.dumps(metadata) + "\n")
        rm.write_file(f"{id}.content", json.dumps({}) + "\n") # this file is required for RM to list file properly
        if metadata["type"] == "DocumentType":
            rm.upload_file(self.path(), f"{id}.pdf")

    def remove(self):
        if self.is_directory():
            os.rmdir(self.path())
        else:
            os.remove(self.path())

# TODO: also return the reason as a string, so it can be printed verbosely?
def sync_action_and_reason(rm_file, pc_file):
    if rm_file and not pc_file:
        return "PULL", "only on RM" # file does not exist on computer, so pull it (for safety, nothing is ever deleted from the remarkable, TODO: change?)

    if pc_file:
        if rm_file and rm_file.is_file(): # if the file is a directory, there is nothing worth updating
            diff = rm_file.last_modified() - pc_file.last_modified()
            if diff > 0:
                return "PULL", f"{+diff}s newer on RM"
            elif diff < 0:
                return "PUSH", f"{-diff}s newer on PC"
        elif not rm_file:
            # file/directory only on PC: was it removed from RM, or created on PC after last sync?
            # use creation time for directories and modification time for files, since directory modification time is dynamic
            # TODO: ^ just return creation time from modification time in class instead?
            #
            # Also, if a user moves a file to the PC directory, the original's modification time can be kept
            # In this case, we want to compare the creation time
            # This SHOULD NOT BE DONE if the file exists on the remarkable, because then downloaded files can be uploaded back!
            pc_time = pc_file.created() if pc_file.is_directory() or pc_file.created() > pc_file.last_modified() else pc_file.last_modified()
            diff = rm.last_sync() - pc_time
            if diff < 0:
                return "PUSH", f"added on PC {-diff}s after last sync"
            else:
                return "DROP", f"deleted on RM in {+diff}s after last sync"

    return "SKIP", "up-to-date"

def sync_files(rm_file, pc_file, dry_run=True):
    action, reason = sync_action_and_reason(rm_file, pc_file)
    if action != "SKIP":
        path = rm_file.path() if rm_file else pc_file.path_on_remarkable()
        prefix = "DRY-" if dry_run else ""
        print(prefix + f"{action} ({reason}): {path}")

        if not dry_run:
            if action == "PULL":
                rm_file.download()
            elif action == "PUSH":
                pc_file.upload()
            elif action == "DROP":
                pc_file.remove()

    return action # let caller determine whether remarkable needs restarting

def sync(dry_run):
    rm_root = RemarkableFile()
    pc_root = ComputerFile(rm.processed_dir_local)

    rm_needs_restart = False
    for rm_file in rm_root.traverse():
        pc_file = rm_file.on_computer()
        action = sync_files(rm_file, pc_file, dry_run=dry_run)
        rm_needs_restart = rm_needs_restart or action == "PUSH"
    for pc_file in pc_root.traverse():
        rm_file = pc_file.on_remarkable()
        if not rm_file: # already processed files on RM in last loop
            action = sync_files(rm_file, pc_file, dry_run=dry_run)
            rm_needs_restart = rm_needs_restart or action == "PUSH"

    if not dry_run:
        rm.write_last_sync()
        if rm_needs_restart:
            rm.restart()

if __name__ == "__main__":
    args = parser.parse_args()
    assert not (getattr(args, "confirm") and getattr(args, "dry_run")), "ambiguous use of --confirm and --dry-run"

    ssh_name = getattr(args, "ssh-name")
    confirm = getattr(args, "confirm")
    dry_run = getattr(args, "dry_run") or confirm

    rm = Remarkable(ssh_name) # TODO: avoid this global variable
    rm.download_metadata()

    sync(dry_run)

    if confirm: # show user changes that will be made (in dry mode), then ask to proceed (in "wet mode")
        answer = input("Proceed with these operations (y/n)? ")
        if answer == "y":
            sync(False)
