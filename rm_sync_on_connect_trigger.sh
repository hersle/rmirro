#!/bin/sh

# This script is invoked with its absolute path by root from the udev rule,
# e.g. $0 = /home/hermasl/Remarkable/rmirro/rm_sync_on_connect_trigger.sh
# Figure out the username and directory that the sync script should be run with
user=$(stat -c %U $0) # e.g. hermasl
dir=$(dirname $0) # e.g. /home/hermasl/Remarkable/rmirro

# Execute the sync script in a terminal emulator
# as the right user and in the right directory,
# requiring the user to confirm its actions
# TODO: instead of hard-coding the Gnome console (kgx), open the user's default terminal emulator?
sudo --user=$user kgx -- sh -c "cd $dir; echo \"Auto-synchronising reMarkable that was just connected with USB\"; echo \"User: \$USER\"; echo \"Directory: \$PWD\"; for i in \$(seq 1 3); do echo Attempt \$i/3:; ./rmirro.py; if [ \$? -eq 0 ]; then break; fi; done" &
#sudo --login --user=hermasl DISPLAY=":0" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$UID/bus" kgx -- sh -c "cd $script_dir; ./rmirro.py --dry-run" & # \; ./rmirro.py --dry-run & # these extra environment variables don't seem to be needed
