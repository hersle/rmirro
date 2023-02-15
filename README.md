# rmirro

![Screenshot](screenshot.png)

`rmirro.py` **synchronizes files between your reMarkable and computer in both directions without cloud access**.
It pulls PDFs of your reMarkable's documents to a folder on your computer,
and pushes PDFs and EPUBs that you add to this folder back to your Remarkable.
Effectively, the tool **integrates your reMarkable with your computer's file system**,
so you can build your own workflow on top.

## Requirements

* [Passwordless SSH access](https://remarkablewiki.com/tech/ssh#passwordless_login_with_ssh_keys) to your reMarkable with `ssh remarkable`.
* Access to the reMarkable's official PDF renderer through its [USB web interface](https://remarkablewiki.com/tech/webinterface)
  **or** any third-party PDF renderer of raw reMarkable files on your computer,
  like [maxio](https://github.com/hersle/maxio/tree/overlay), [rmrl](https://github.com/rschroll/rmrl) or [rmc](https://github.com/ricklupton/rmc).

## Usage and operation

Just run `rmirro.py`. Read `rmirro.py --help` to see how you can change its default behavior.

It synchronizes files between the reMarkable (RM) and the computer (PC) folder `./remarkable/`.
The first run processes *all* files on the reMarkable and may take a long time,
but following runs skip unchanged files and are quicker.
What is done to each file depends on where it is present and when it was last modified:

| If a file is ...                                 | then `rmirro.py` will ...                                    |
|:-------------------------------------------------|:-------------------------------------------------------------|
| added/modified on RM (more recently than on PC), | **pull** it to PC.                                           |
| added/modified on PC (more recently than on RM), | **push** it to RM.                                           |
| deleted on RM,                                   | **drop** (delete) it on PC, too.                             |
| deleted on PC,                                   | **pull** it to PC again (*not* delete it on RM, for safety). |

Before acting on files, the program presents its intentions and prompts the user for confirmation.
Beware that it may have bugs and has the potential to overwrite and delete files on your reMarkable and computer!
Therefore, `rmirro.py` keeps a [raw backup](https://remarkablewiki.com/tech/file_transfer#making_local_backups) of your reMarkable in `./remarkable_backup/`.

### Auto-synchronize when the reMarkable is connected by USB cable

Run `rm_sync_on_connect_setup.sh` with root access to install an [udev](https://en.wikipedia.org/wiki/Udev) rule
that automatically runs `rmirro.py` when your reMarkable is connected to the computer with a USB cable.

---

`rmirro` is what you get by shifting the characters in `mirror` cyclically one step to the right.
