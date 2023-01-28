# rmirro

`rmirro.py` is a Python script that maintains a live mirror image
of your reMarkable's files in a folder on your computer that directly matches its file structure.
Documents on the reMarkable are downloaded as PDFs to this folder,
and documents put in the folder are uploaded to the reMarkable.

## Requirements
`rmirro.py` reads your reMarkable's file system structure and downloads and uploads files to it over SSH and USB.
* The reMarkable must be connected to your computer with a USB cable.
* The reMarkable's [USB web interface](https://remarkablewiki.com/tech/webinterface) must be enabled.
* The reMarkable must be accessible through [passwordless SSH login](https://remarkablewiki.com/tech/ssh#passwordless_login_with_ssh_keys) (by running e.g. `ssh remarkable`).

## Operation
`rmirro.py` creates a folder on your computer, by default named `remarkable/`, from which you can read and upload documents to your reMarkable.
Documents and folders that have been added, modified or removed on the reMarkable or computer since the last run are transfered to the other device.
The program traverses files and folders on both the reMarkable (RM) and the computer (PC), and takes the following actions:

* File/folder exist *only on RM*:
  - Always **download it to PC**.
* File/folder exists *only on PC*:
  - If it was added *after the last sync*, **upload it to RM**.
  - If it was added *before the last sync*, **remove it from PC**.
* File/folder exists on *both RM and PC*:
  - If it is newer on RM, **download it to PC**.
  - If it is newer on PC, **upload it to RM**.

The program prompts the user for confirmation before proceeding and executing operations.
**However, it can potentially overwrite or delete files on your computer or reMarkable.**
I do not guarantee that it works as expected, so back up your data and use it at your own risk!

## Synchronise automatically when connected with USB

Run `rm_sync_on_connect_setup.sh` to install an [udev](https://en.wikipedia.org/wiki/Udev) rule on your system (requires root access)
that automatically runs `rmirro.py` when the reMarkable is connected to your computer.
