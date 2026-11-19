# Tapo Hotkeys

Control a TP-Link Tapo L535E smart bulb from the Windows keyboard. AutoHotkey v2 captures your shortcuts, and a background Python service sends commands to the bulb over your local network.

## Features

- Toggle power, adjust brightness, recall six bulb presets, and select three built-in colors.
- Prepare the device connection at startup and reuse it for subsequent commands.
- Use the latest of consecutive built-in color commands that are still waiting in the queue. Presets, brightness, and power commands remain in order.
- Send power and color together so a color shortcut can turn on the bulb without an initial white flash.

## Requirements

- Windows and [AutoHotkey v2](https://www.autohotkey.com/).
- [Python 3.14](https://www.python.org/downloads/windows/). The launcher expects a per-user installation at `%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe`.
- Python packages `python-kasa==0.12.0` and `keyring`.
- A Tapo L535E set up in the Tapo app, its local IP address, and a Windows PC that can reach it over the local network. Other models may expose different features.
- Git if you use the clone command below. You can also download the repository ZIP from GitHub and extract it to a writable folder.

## Installation

1. Install Python 3.14 and AutoHotkey v2.
2. Open PowerShell and get the project. If you downloaded the ZIP, open PowerShell in the extracted project folder instead.

   ```powershell
   git clone https://github.com/barisbargun/tapo_hotkeys.git
   Set-Location tapo_hotkeys
   ```

3. Install the Python dependencies using the same installation the launcher uses.

   ```powershell
   $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
   & $python --version
   & $python -m pip install 'python-kasa==0.12.0' keyring
   ```

   For a custom Python installation, set `$python` to its `python.exe` path and update the `pythonw` path in [TapoHotkeys.ahk](TapoHotkeys.ahk) to the matching `pythonw.exe`.

4. Look up the bulb's local IP address in your router's connected-device list. Open [tapo_service.py](tapo_service.py), replace the value of `HOST` with that address, and save the change locally. A DHCP reservation can keep the address stable.
5. Configure your Tapo credentials, then launch the hotkey script as described below.

## Configure Tapo credentials

In the same PowerShell window, run this command as the Windows user who will run the hotkeys.

```powershell
& $python .\setup_credentials.py
```

Enter the email address and password for the Tapo account associated with the bulb. The password prompt hides what you type. The script saves both entries under `TapoHotkeys` in Windows Credential Manager. Run the command again to update them if your credentials change.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Win+Ctrl+0` | Toggle power |
| `Win+Ctrl+1` through `Win+Ctrl+6` | Apply the corresponding bulb light preset |
| `Win+Ctrl+7` | Red at 5% brightness |
| `Win+Ctrl+8` | Green at 50% brightness |
| `Win+Ctrl+9` | Pink-magenta at 50% brightness |
| `Win+Ctrl+↑` | Increase brightness by 10 percentage points |
| `Win+Ctrl+↓` | Decrease brightness by 10 percentage points |

Brightness stays between 1% and 100%. A brightness shortcut turns the bulb on if it is off. To customize a shortcut, edit its `Hotkey` binding in [TapoHotkeys.ahk](TapoHotkeys.ahk) and relaunch the script.

### Examples

- Press `Win+Ctrl+7` to turn on a dim red light, then press `Win+Ctrl+↑` to raise it to 15%.
- Press `Win+Ctrl+2` to recall the bulb's second light preset.
- If you press `7`, `8`, and `9` rapidly while holding `Win+Ctrl`, the latest color wins among those still queued. An earlier color command already sent to the bulb may still take effect first.

## Start and stop the service

- **Start** by double-clicking [TapoHotkeys.ahk](TapoHotkeys.ahk). AutoHotkey registers the shortcuts and launches the Python service in the background. `Device ready` in `tapo_service.log` indicates that the initial connection succeeded.
- **Stop** by double-clicking [Stop_Controller.ahk](Stop_Controller.ahk). It queues a stop request. Wait for `Stopped` in `tapo_service.log` before restarting. To disable the shortcuts as well, exit Tapo Hotkeys from the AutoHotkey tray menu.
- **Restart** by launching `TapoHotkeys.ahk` again after the service stops.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| The launcher reports that Python or the service file is missing | Verify the `pythonw.exe` path and keep both AutoHotkey scripts next to `tapo_service.py`. |
| The service exits before writing a log | Run `& $python .\tapo_service.py` in PowerShell to see startup errors. If it reports `ModuleNotFoundError`, install the packages with the `python.exe` that matches the launcher's `pythonw.exe`. |
| Credentials are missing or rejected | Run `setup_credentials.py` again under the same Windows account and verify your Tapo sign-in. |
| Discovery or connection times out | Check that the bulb is powered, `HOST` is current, and the PC can reach the bulb. Guest Wi-Fi or client isolation can block local device traffic. A failed connection attempt discards waiting commands. Press the shortcut again after restoring connectivity. |
| A numbered preset fails | Check that the bulb exposes the corresponding light preset. The log records invalid device actions. |
| The first toggle after using the Tapo app seems out of sync | The service caches power state between commands. Restart the service to refresh it from the bulb. |

## Security and privacy

The service retrieves credentials from Windows Credential Manager and uses them to authenticate to the bulb. Keep account details out of source files, command-line arguments, and commits. Keep your local `HOST` edit out of shared commits when it contains your network configuration.

The service uses a loopback-only socket to prevent duplicate local instances. AutoHotkey and Python exchange commands through the local `pending` folder, so keep the project in a directory writable only by trusted users. Review `tapo_service.log` before sharing it because connection errors can disclose local network details.
