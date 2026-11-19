#Requires AutoHotkey v2.0
#SingleInstance Force

; Place this script next to tapo_service.py
pythonw := EnvGet("LOCALAPPDATA") "\Programs\Python\Python314\pythonw.exe"
service := A_ScriptDir "\tapo_service.py"
queue := A_ScriptDir "\pending"

if !FileExist(pythonw) || !FileExist(service) {
    MsgBox "Python veya tapo_service.py bulunamadi."
    ExitApp
}
DirCreate(queue)
Run('"' pythonw '" "' service '"', A_ScriptDir, "Hide")

Loop 9 {
    presetIndex := A_Index
    Hotkey("#^" presetIndex, QueueAction.Bind(presetIndex))
}
Hotkey("#^0", QueueAction.Bind(0))
Hotkey("#^Up", QueueAction.Bind("UP"))
Hotkey("#^Down", QueueAction.Bind("DOWN"))

QueueAction(action, *) {
    global queue
    filename := queue "\" A_NowUTC "_" A_TickCount "_" Random(100000, 999999) ".cmd"
    FileAppend(String(action), filename, "UTF-8-RAW")
}
