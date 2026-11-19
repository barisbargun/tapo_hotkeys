#Requires AutoHotkey v2.0
DirCreate(A_ScriptDir "\pending")
filename := A_ScriptDir "\pending\stop_" A_TickCount "_" Random(100000, 999999)
FileAppend("STOP", filename ".tmp", "UTF-8-RAW")
FileMove(filename ".tmp", filename ".cmd")
MsgBox "Kapatma komutu gonderildi. TapoHotkeys.ahk yeniden acilinca servis tekrar baslar."
