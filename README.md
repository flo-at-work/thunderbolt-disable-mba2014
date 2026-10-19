Linux service and script to disable Thunderbolt on MacBook Air 11" 2014

On Linux, the only way to truly disable (electrically) Thunderbolt on a MacBook Air 11" 2014 to decrease power consumption is to use the kernel flag acpi_osi=!Darwin, other ways like modprobe blacklisting or pcie_ports=compat kernel flag can disable the use of the Thunderbolt but doesn't stop the chip to consume power.
Unfortunately this flag comes with some drawbacks like impossibility to set battery charge/discharge thresholds and other Apple related optimizations which has been done under Linux.

What this kernel flag does is telling to the Apple firmware that the running OS isn't macOS (non-Darwin), then the firmware activate sequences of the DSDT (see: https://wiki.archlinux.org/title/DSDT) specific to Windows, and at that time Apple hasn't released a Thunderbolt driver for Windows, hence they completely disabled it for this OS.

I propose here a solution which is to reproduce the "non-Darwin" (DTLK) sequence from the DSDT to disable the Thunderbolt but keeping at the same other Apple related optimizations for Linux.

It comes with a python script and a service which runs at boot and after waking from sleep. The script tells to the MacBook to activate the "non-Darwin" sequence related to the Thunderbolt, which then disable completely Thunderbolt.

To install it:

1. copy the 'tb-off.py' into '/usr/local/bin/' folder
2. copy the 'tb-off.service' into '/etc/systemd/system/'
3. run: 'sudo systemctl daemon-reload' followed by 'sudo systemctl enable tb-off.service' and by 'sudo systemctl start tb-off.service'
