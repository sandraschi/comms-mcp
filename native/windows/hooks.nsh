; Kill UI + backend before install/uninstall (backend locks resources/comms-mcp-backend.exe).
!macro KillCommsMcpFleetProcesses
  DetailPrint "Stopping Comms MCP and backend..."
  ExecWait 'taskkill /F /IM comms-mcp-backend.exe /T' $0
  ExecWait 'taskkill /F /IM comms-mcp-native.exe /T' $0
  !if "${INSTALLMODE}" == "currentUser"
    nsis_tauri_utils::KillProcessCurrentUser "comms-mcp-backend.exe"
    Pop $0
    nsis_tauri_utils::KillProcessCurrentUser "comms-mcp-native.exe"
    Pop $0
  !else
    nsis_tauri_utils::KillProcess "comms-mcp-backend.exe"
    Pop $0
    nsis_tauri_utils::KillProcess "comms-mcp-native.exe"
    Pop $0
  !endif
  Sleep 2000
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro KillCommsMcpFleetProcesses
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro KillCommsMcpFleetProcesses
!macroend
