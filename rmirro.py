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

# TODO: optimize!!! less file access
# TODO: what about using DP in RemarkableFile?
class Remarkable:
    def __init__(self, ssh_name):
        self.ssh_name = ssh_name
        self.ssh_ip = pc_run(f"ssh {self.ssh_name} -v exit 2>&1 | grep 'Connecting to' | cut -d' ' -f4") # e.g. 10.11.99.1
        self.raw_dir_local = os.path.abspath(f"{self.ssh_name}_metadata_rewrite")
        self.raw_dir_remote = "/home/root/.local/share/remarkable/xochitl"
        self.processed_dir_local = f"{self.ssh_name}_rewrite"

rm = Remarkable("remarkable")

class RemarkableFile:
    def __init__(self, id=""):
        self.is_root = id == ""
        self.id = id

    # TODO: make faster
    def metadata(self):
        with open(rm.raw_dir_local + "/" + self.id + ".metadata", "r") as file:
            metadata = json.loads(file.read())
        return metadata

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
        return RemarkableFile(parent_id)

    def name(self):
        if self.is_root:
            return ""
        return self.metadata()["visibleName"]

    def path(self):
        if self.is_root:
            return ""
        path = self.parent().path() + "/" + self.name()
        if self.is_file():
            path += ".pdf" # TODO: .pdf only?
        return path

    # TODO: make use pythonic for ... in self:
    def traverse_top_down(self, func):
        terminate = func(self)
        if terminate:
            return # return early, if desired by func
        for child in self.children():
            child.traverse_top_down(func)

    def traverse_bottom_up(self, func):
        for child in self.children():
            child.traverse_bottom_up(func)
        terminate = func(self)
        if terminate:
            return # return early, if desired by func

    def find(self, path):
        file = None
        def func(candidate_file):
            nonlocal file # modify variable outside function
            if candidate_file.path() == "/" + path: # TODO: how to handle / with root?
                file = candidate_file
                return True
            else:
                return False
        self.traverse_top_down(func)
        return file

    def list(self):
        def func(file):
            print(file.path())
        self.traverse_top_down(func)

    def is_directory(self):
        return self.is_root or self.metadata()["type"] == "CollectionType"

    def is_file(self):
        # TODO: verify that it is equivalent to not is_directory()
        return not self.is_root and self.metadata()["type"] == "DocumentType"

    def last_modified(self):
        if self.is_root:
            return 0 # TODO: valid?
        return int(self.metadata()["lastModified"]) # ms

    def last_accessed(self):
        if self.is_root:
            return 0 # TODO: valid?
        return int(self.metadata()["lastOpened"]) # ms

    def download(self, recursive=False, verbose=False):
        print("PULL", self.path())
        path_local = rm.processed_dir_local + self.path()
        if self.is_directory():
            os.makedirs(path_local, exist_ok=True)
        else: # is file
            url = f"http://{rm.ssh_ip}/download/{self.id}/placeholder"
            urllib.request.urlretrieve(url, filename=path_local)
            atime = self.last_accessed() / 1000 # s
            mtime = self.last_modified() / 1000 # s
            os.utime(path_local, (atime, mtime)) # sync with access/modification times from RM

        if recursive:
            for child in self.children():
                child.download()


if __name__ == "__main__":
    rm_root = RemarkableFile()
    #rm_root.download(recursive=True, verbose=True)
    rm_root.list()
    #print(rm_root.find("AST4320").last_modified())
    #rm_root.list()
    #for child in rm_root.children():
        #print(child.path())
