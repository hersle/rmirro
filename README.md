# rmirro

![Screenshot](screenshot.png)

`rmirro.py` is a Python script that maintains a live mirror image
of your reMarkable's files in a folder on your computer that directly matches its file structure.
Documents on the reMarkable are downloaded as PDFs to this folder,
and documents put in the folder are uploaded to the reMarkable.

"rmirro" is what you get by shifting the characters in "mirror" cyclically one step to the right.

## Requirements
`rmirro.py` reads your reMarkable's file structure and downloads and uploads files to it over SSH and USB.
* The reMarkable must be connected to your computer with a USB cable.
* The reMarkable's [USB web interface](https://remarkablewiki.com/tech/webinterface) must be enabled.
* The reMarkable must be accessible through [passwordless SSH login](https://remarkablewiki.com/tech/ssh#passwordless_login_with_ssh_keys) (by running e.g. `ssh remarkable`).

## Operation
`rmirro.py` creates a folder on your computer, by default named `remarkable/`, from which you can read and upload documents to your reMarkable.
Documents and folders that have been added, modified or removed on the reMarkable or computer since the last run are transferred to or removed from the other device.
More specifically, the program traverses files and folders on both the reMarkable (RM) and the computer (PC), and takes the following actions depending on where they are present and when they were last modified:

|                                                  | <span style="color: green">⏺</span> **On PC** | <span style="color: red">⏺</span> **Not on PC** |
|--------------------------------------------------|------------------------------------------------|--------------------------------------------------|
| <span style="color: green">⏺</span> **On RM**   | Download/upload if newer on RM/PC              | Download                                         |
| <span style="color: red">⏺</span> **Not on RM** | Upload/remove if added after/before last sync  |                                                  |

## Auto-synchronise when connecting USB cable

Run `rm_sync_on_connect_setup.sh` to install an [udev](https://en.wikipedia.org/wiki/Udev) rule on your system (requires root access)
that automatically runs `rmirro.py` when the reMarkable is connected to your computer.

## Disclaimer

The program prompts the user for confirmation before proceeding and executing operations.
**However, it can potentially overwrite or delete files on your computer or reMarkable.**
I do not guarantee that it works as expected, so back up your data and use it at your own risk!
