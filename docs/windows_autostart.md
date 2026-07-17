# Windows 11 Autostart

This setup starts the BRIC Lightwall web app automatically whenever the Windows
11 Mini-PC boots. It can run headless: the Mini-PC controls the Pis over
Ethernet, while your iPhone opens the web UI over Wi-Fi.

The recommended headless startup command is:

```text
python tools/webapp/app.py --interface Ethernet --web-host 0.0.0.0
```

`--interface Ethernet` tells the app to discover and drive the Pis through the
TP-Link Ethernet switch. `--web-host 0.0.0.0` lets phones/tablets on Wi-Fi open
the web UI. The web UI is still available locally at `http://localhost:8080`.

## 1. Verify The App Works Manually

Open PowerShell or Git Bash on the Mini-PC:

```powershell
cd $env:USERPROFILE\bric-lightwall
python tools/discover_tiles.py --interface Ethernet --timeout 2.0
python tools/webapp/app.py --interface Ethernet --web-host 0.0.0.0
```

Open this on the Mini-PC:

```text
http://localhost:8080
```

From the iPhone, join the same Wi-Fi network as the Mini-PC and open the
Mini-PC's Wi-Fi IP address. For example, if `ipconfig` shows the Mini-PC Wi-Fi
address as `192.168.1.65`, open:

```text
http://192.168.1.65:8080
```

Stop the manual server with `Ctrl+C` before installing the startup task.

## 2. Install The Startup Task

Open PowerShell as Administrator:

1. Open Start.
2. Type `PowerShell`.
3. Right-click Windows PowerShell.
4. Choose `Run as administrator`.

Run:

```powershell
cd $env:USERPROFILE\bric-lightwall
powershell -ExecutionPolicy Bypass -File .\scripts\windows_install_webapp_startup.ps1 -Interface Ethernet -WebHost 0.0.0.0
```

The installer creates a Scheduled Task named `BRIC Lightwall Web App`. It runs
as `SYSTEM` at Windows startup, so it does not require Git Bash to be open and
does not require the `BRIC-ADMIN` user to be logged in.

The installer also adds Windows Firewall rules for TCP port `8080` and Python
UDP discovery on Private networks. Make sure the Mini-PC Wi-Fi network is marked
Private:

```powershell
Get-NetConnectionProfile
Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
```

If another computer on the same Wi-Fi cannot open the web UI, replace the
firewall rule and restart the task:

```powershell
Remove-NetFirewallRule -DisplayName "BRIC Lightwall Web App TCP 8080" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "BRIC Lightwall Web App TCP 8080" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080 -Profile Any
Stop-ScheduledTask -TaskName "BRIC Lightwall Web App"
Start-ScheduledTask -TaskName "BRIC Lightwall Web App"
netstat -ano | findstr :8080
```

From the Mac, test the port:

```bash
nc -vz 192.168.1.65 8080
```

If the port still does not connect, check that the Mac/iPhone and Mini-PC are
not on a guest Wi-Fi network with client isolation enabled.

The installer automatically uses `.venv\Scripts\python.exe` if it exists. If
Python is somewhere else, pass it explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows_install_webapp_startup.ps1 -Interface Ethernet -WebHost 0.0.0.0 -Python "C:\Path\To\python.exe"
```

Logs are written to:

```text
logs\webapp.log
```

Web server output is written to:

```text
logs\webapp.stdout.log
logs\webapp.stderr.log
```

Game subprocess output is written to:

```text
logs\games\pong.stdout.log
logs\games\pong.stderr.log
logs\games\invaders.stdout.log
logs\games\invaders.stderr.log
logs\games\color_game.stdout.log
logs\games\color_game.stderr.log
```

## Repair Existing Startup Task

If `logs\webapp.log` shows `Python=C`, update the repo and reinstall the task.
That means an older launcher script truncated the Python path.

In Administrator PowerShell:

```powershell
cd $env:USERPROFILE\bric-lightwall
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\windows_uninstall_webapp_startup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\windows_install_webapp_startup.ps1 -Interface Ethernet -WebHost 0.0.0.0
```

Verify that the new log says `--web-host 0.0.0.0` and shows a full Python path,
not just `Python=C`:

```powershell
Get-Content .\logs\webapp.log -Tail 80
Get-Content .\logs\webapp.stdout.log -Tail 80
Get-Content .\logs\webapp.stderr.log -Tail 80
netstat -ano | findstr :8080
```

If `webapp.log` shows Flask's normal development-server warning as an `ERROR`,
pull the latest launcher and restart the scheduled task:

```powershell
cd $env:USERPROFILE\bric-lightwall
git pull
Stop-ScheduledTask -TaskName "BRIC Lightwall Web App"
Start-ScheduledTask -TaskName "BRIC Lightwall Web App"
```

## 3. Verify The Task

In Administrator PowerShell:

```powershell
Get-ScheduledTask -TaskName "BRIC Lightwall Web App"
Get-ScheduledTaskInfo -TaskName "BRIC Lightwall Web App"
Get-Content .\logs\webapp.log -Tail 40
```

Open:

```text
http://localhost:8080
```

From the iPhone, open:

```text
http://<mini-pc-wifi-ip>:8080
```

Reboot once and verify it comes back automatically:

```powershell
Restart-Computer
```

After Windows finishes booting, open `http://localhost:8080` again.

## 4. Remove The Startup Task

If needed, remove it from Administrator PowerShell:

```powershell
cd $env:USERPROFILE\bric-lightwall
powershell -ExecutionPolicy Bypass -File .\scripts\windows_uninstall_webapp_startup.ps1
```

## 5. Make The Mini-PC Power On When Plugged In

This is a BIOS/UEFI setting, not a Windows setting. The exact menu names vary
by Mini-PC, but the setting is usually one of:

```text
Restore AC Power Loss
AC Back
After Power Failure
Power On After Power Fail
State After G3
```

Set it to:

```text
Power On
Always On
Last State
```

Prefer `Power On` or `Always On` if available.

To enter BIOS/UEFI from Windows 11:

1. Open `Settings`.
2. Go to `System` -> `Recovery`.
3. Under `Advanced startup`, click `Restart now`.
4. Choose `Troubleshoot`.
5. Choose `Advanced options`.
6. Choose `UEFI Firmware Settings`.
7. Click `Restart`.
8. Find the power-loss setting, set it to `Power On`, then save and exit.

Alternative: restart the Mini-PC and repeatedly press `Del`, `F2`, `F7`, or
`Esc` during boot. The correct key depends on the Mini-PC vendor.

Test it:

1. Shut Windows down.
2. Unplug the Mini-PC power cable for 10 seconds.
3. Plug power back in.
4. Confirm the Mini-PC powers itself on.
5. Confirm `http://localhost:8080` works after boot.
