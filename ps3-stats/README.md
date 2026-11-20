# PS3 Stats

PS3 Stats is a read-only homebrew app for the XMB. In version 1.3, press **Square** after the dashboard opens to check free internal storage once per launch. Press **Cross** to enable live CELL and RSX temperatures, or **Circle** to exit. A missing or invalid measurement appears as **Unavailable**.

The first hardware test target is **CFW 4.93**. The app reads the temperatures directly and does not require webMAN MOD. It does not read fan speed, alter fan settings, or open a network connection.

## Build

With a PS3DEV toolchain and PSL1GHT installed, set `PS3DEV` and `PSL1GHT` to the toolchain and SDK directories. Run `make -C ps3-stats` from the repository root. The PSL1GHT build generates `PS3_Stats.pkg` and `PS3_Stats.gnpdrm.pkg`.

## Install and check

Download `PS3_Stats.pkg` from the repository’s [downloads folder](../downloads) (the finalized CFW package), or use your local build’s `PS3_Stats.gnpdrm.pkg`. Copy it to a USB drive and install it through **Game → Package Manager → Install Package Files** on your CFW console. Start **PS3 Stats** from the Game column. First confirm that the dashboard appears and Circle returns to the XMB. On a subsequent launch, Cross enables temperature readings.

Version 1.2 displayed live CELL and RSX readings and exited to the XMB on a CFW 4.93 console. The v1.3 storage check still needs a console test.

## If startup goes black

Version 1.3 checks storage only after you press Square. If there is a freeze after pressing it, leave the storage check unused on subsequent launches. If the console stops responding, hold the physical power button until it shuts off. On restart, let any file-system check finish.

If you can read files on the console after reboot, the last line in `/dev_hdd0/game/ZSTATS001/USRDIR/startup.log` identifies the last startup step the app reached. Each launch starts a fresh log.
