#!/bin/sh

# create udev rule tailored for current user
script_path=$(realpath rm_sync_on_connect_trigger.sh) # full path to script
rule_path=rm_sync_on_connect.rules
printf 'ACTION=="add", SUBSYSTEMS=="usb", ATTR{manufacturer}=="reMarkable", ' > $rule_path
printf "RUN+=\"/bin/sh $script_path\"\n" >> $rule_path

echo "Generated udev rule:"
cat $rule_path
read -p "Install it to $/etc/udev/rules.d/$rule_path (y/n)? " answer

if [ $answer = "y" ]; then
	sudo mv $rule_path /etc/udev/rules.d/
	sudo udevadm control --reload-rules
fi
