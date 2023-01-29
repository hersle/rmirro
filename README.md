# rmirro

![Screenshot](screenshot.png)

`rmirro.py` **synchronizes files between your reMarkable and computer in both directions** without cloud access.
It **pulls PDFs** of your Remarkable's documents to a folder on your computer,
and **pushes PDFs and EPUBs** that you add to this folder back to the Remarkable.
Effectively, it **integrates your reMarkable with your computer's native file system,**
giving you the flexibility to build your workflow with whichever file explorer, document viewer and additional tools you want.

(`rmirro` is what you get by shifting the characters in `mirror` cyclically one step to the right.)

## Requirements

* [Passwordless SSH access](https://remarkablewiki.com/tech/ssh#passwordless_login_with_ssh_keys) to your reMarkable with `ssh remarkable`.
* Access to the [Remarkable's USB web interface](https://remarkablewiki.com/tech/webinterface)
  ~~**or** a command line program on your computer that converts raw reMarkable files to PDF (**TODO**)~~.

## Usage and operation

1. Run `git clone https://github.com/hersle/rmirro.git` to download this program.
2. Run `./rmirro.py` to pull *all* your reMarkable's documents into `./remarkable/` (this can take a while).
3. Work on your reMarkable, and add PDFs and EPUBs to `./remarkable/`.
4. Run `./rmirro.py` again to pull changes and push documents added since last time (this skips up-to-date files and runs faster).
5. Go to 3.

During synchronization, a file is

* **pulled** from the reMarkable (RM),
* **pushed** to the computer (PC) or
* **dropped** from the *computer*,

depending on where it is present and when it was last modified:

|                  | 🟢 **On PC**                                      | 🔴 **Not on PC** |
|------------------|:-------------------------------------------------:|:----------------:|
| 🟢 **On RM**     | **Pull**/**push** if newer on RM/PC               | **Pull**         |
| 🔴 **Not on RM** | **Push**/**drop** if added after/before last sync |                  |

The program presents its intentions and prompts for confirmation before executing impactful commands.
However, it is a hobby project with 0 or more bugs, so *beware that it has the potential to overwrite and delete files on your reMarkable and computer!*

### Auto-synchronize when the reMarkable is connected by USB cable

Run `rm_sync_on_connect_setup.sh` to install an [udev](https://en.wikipedia.org/wiki/Udev) rule on your system (requires root access)
that automatically runs `rmirro.py` when the reMarkable is connected to your computer with a USB cable.
