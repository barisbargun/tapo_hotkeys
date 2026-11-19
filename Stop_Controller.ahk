#Requires AutoHotkey v2.0
DirCreate(A_ScriptDir "\pending")
FileAppend("STOP", A_ScriptDir "\pending\stop_" A_TickCount ".cmd", "UTF-8-RAW")
MsgBox "Kapatma komutu gonderildi. TapoHotkeys.ahk yeniden acilinca servis tekrar baslar."
