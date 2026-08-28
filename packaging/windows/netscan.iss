; ============================================================
;  NetScan — instalador de Windows (Inno Setup)
;
;  Compilar:
;    1. Instala Inno Setup 6:  winget install JRSoftware.InnoSetup
;    2. Desde la raíz del repo:
;         iscc packaging\windows\netscan.iss
;    3. Sale: packaging\windows\Output\NetScan-Setup.exe
;
;  El .exe resultante:
;    - Aparece en "Agregar o quitar programas" (con desinstalador).
;    - Copia el proyecto a Archivos de programa\NetScan.
;    - Ejecuta install.bat (crea el venv, instala deps Python/Node,
;      compila el dashboard) al final de la instalación.
;    - Crea accesos directos en el menú Inicio y (opcional) escritorio
;      que lanzan "netscan up" (API + dashboard + navegador).
; ============================================================

#define MyAppName "NetScan"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "NetScan contributors"
#define MyAppURL "https://github.com/abarriuso/netscan"

[Setup]
AppId={{4E3B7C1A-9D2F-4A6B-8C5E-NETSCAN000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\NetScan
DefaultGroupName=NetScan
DisableProgramGroupPage=yes
OutputBaseFilename=NetScan-Setup
OutputDir=Output
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; El venv/build y el auto-elevado del ARP requieren admin.
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=NetScan
SetupLogging=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "minimal"; Description: "Instalación mínima (sin nmap/RustScan/nuclei)"; GroupDescription: "Opciones:"; Flags: unchecked

[Files]
; Copia todo el árbol del proyecto EXCEPTO artefactos de build/entornos.
; (Ejecutar iscc desde la raíz del repo para que estas rutas relativas resuelvan.)
Source: "..\..\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs; \
  Excludes: "\.git\*,\.git,\.github\*,_to_delete\*,backend\.venv\*,frontend\node_modules\*,*.pyc,__pycache__\*,\.mypy_cache\*,\.ruff_cache\*,\.pytest_cache\*,packaging\windows\Output\*,*.log,data\*.db*,netscan-src.tgz,netscan-update.tgz"

[Icons]
; Lanzador principal: "netscan up" (todo en uno).
Name: "{group}\NetScan (Dashboard)"; Filename: "{app}\netscan.bat"; Parameters: "up"; WorkingDir: "{app}"; Comment: "Arranca API + dashboard y abre el navegador"
Name: "{group}\NetScan — Consola"; Filename: "{cmd}"; Parameters: "/k cd /d ""{app}"" && netscan.bat doctor"; WorkingDir: "{app}"; Comment: "Terminal de NetScan"
Name: "{group}\Desinstalar NetScan"; Filename: "{uninstallexe}"
Name: "{autodesktop}\NetScan"; Filename: "{app}\netscan.bat"; Parameters: "up"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Preparación silenciosa (venv + deps + build). NETSCAN_NONINTERACTIVE evita el 'pause'.
Filename: "{cmd}"; Parameters: "/c set NETSCAN_NONINTERACTIVE=1&& ""{app}\install.bat"" {code:GetMinimalFlag}"; \
  WorkingDir: "{app}"; StatusMsg: "Instalando dependencias y compilando el dashboard (puede tardar varios minutos)..."; \
  Flags: waituntilterminated runhidden
; Ofrecer lanzar al terminar.
Filename: "{app}\netscan.bat"; Parameters: "up"; Description: "Lanzar NetScan ahora"; \
  WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\backend\.venv"
Type: filesandordirs; Name: "{app}\frontend\node_modules"
Type: filesandordirs; Name: "{app}\frontend\dist"
Type: filesandordirs; Name: "{app}\data"

[Code]
function GetMinimalFlag(Param: String): String;
begin
  if WizardIsTaskSelected('minimal') then
    Result := '--minimal'
  else
    Result := '';
end;
