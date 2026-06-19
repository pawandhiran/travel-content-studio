; Travel Content Studio - Inno Setup Script
; Builds TravelContentStudioSetup.exe

#define MyAppName "Travel Content Studio"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Travel Content Studio"
#define MyAppURL "https://github.com/travel-content-studio"
#define MyAppExeName "Travel Content Studio.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=TravelContentStudioSetup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitModeOnly=x64compatible
MinVersion=10.0.17763

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; Electron app (electron-builder win-unpacked output)
Source: "..\release\win-unpacked\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Python backend (PyInstaller bundle)
Source: "..\backend\dist\travel-content-studio-backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs
; FFmpeg binaries
Source: "deps\ffmpeg.exe"; DestDir: "{app}\bin"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}'))
Source: "deps\ffprobe.exe"; DestDir: "{app}\bin"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}'))

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Travel Content Studio"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\backend"
Type: filesandordirs; Name: "{app}\bin"
Type: filesandordirs; Name: "{app}\locales"
Type: filesandordirs; Name: "{app}\resources"
Type: dirifempty; Name: "{app}"
Type: filesandordirs; Name: "{localappdata}\travel-content-studio"

[Code]
const
  MIN_RAM_GB = 8;
  MIN_DISK_GB = 20;
  OLLAMA_INSTALLER_URL = 'https://ollama.com/download/OllamaSetup.exe';

var
  DownloadPage: TDownloadWizardPage;

function GetSystemRAMGB: Integer;
var
  WMI, Items, Item: Variant;
  TotalBytes: Int64;
begin
  try
    WMI := CreateOleObject('WbemScripting.SWbemLocator');
    WMI := WMI.ConnectServer('.', 'root\cimv2');
    Items := WMI.ExecQuery('SELECT TotalPhysicalMemory FROM Win32_ComputerSystem');
    Item := Items.ItemIndex(0);
    TotalBytes := Item.TotalPhysicalMemory;
    Result := TotalBytes div (1024 * 1024 * 1024);
  except
    Result := 0;
  end;
end;

function GetFreeDiskSpaceGB(Path: String): Integer;
var
  FreeBytes, TotalBytes: Int64;
begin
  if GetSpaceOnDisk(ExtractFileDrive(Path), True, FreeBytes, TotalBytes) then
    Result := FreeBytes div (1024 * 1024 * 1024)
  else
    Result := 0;
end;

function HasNvidiaGPU: Boolean;
var
  WMI, Items: Variant;
begin
  try
    WMI := CreateOleObject('WbemScripting.SWbemLocator');
    WMI := WMI.ConnectServer('.', 'root\cimv2');
    Items := WMI.ExecQuery('SELECT Name FROM Win32_VideoController WHERE Name LIKE ''%NVIDIA%''');
    Result := Items.Count > 0;
  except
    Result := False;
  end;
end;

function IsOllamaInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe')) or
            FileExists('C:\Program Files\Ollama\ollama.exe');
end;

function GetOllamaPath: String;
begin
  if FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe')) then
    Result := ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe')
  else if FileExists('C:\Program Files\Ollama\ollama.exe') then
    Result := 'C:\Program Files\Ollama\ollama.exe'
  else
    Result := '';
end;

function GetRecommendedModel: String;
var
  RAM: Integer;
begin
  RAM := GetSystemRAMGB;
  if RAM >= 32 then
    Result := 'qwen3:32b'
  else if RAM >= 16 then
    Result := 'qwen3:14b'
  else
    Result := 'qwen3:8b';
end;

function InitializeSetup: Boolean;
var
  RAM: Integer;
  Disk: Integer;
begin
  Result := True;

  if not IsWin64 then
  begin
    MsgBox('Travel Content Studio requires 64-bit Windows 10 or later.', mbError, MB_OK);
    Result := False;
    Exit;
  end;

  RAM := GetSystemRAMGB;
  if RAM < MIN_RAM_GB then
  begin
    if MsgBox(Format('Your system has %d GB RAM. Minimum recommended is %d GB. Continue anyway?',
      [RAM, MIN_RAM_GB]), mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;

  Disk := GetFreeDiskSpaceGB(ExpandConstant('{autopf}'));
  if Disk < MIN_DISK_GB then
  begin
    MsgBox(Format('Insufficient disk space. Need at least %d GB free, found %d GB.',
      [MIN_DISK_GB, Disk]), mbError, MB_OK);
    Result := False;
    Exit;
  end;

  if not HasNvidiaGPU then
  begin
    MsgBox('No NVIDIA GPU detected. The application will run in CPU mode, which is significantly slower. ' +
           'An NVIDIA GPU with 4GB+ VRAM is recommended for optimal performance.',
           mbInformation, MB_OK);
  end;
end;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  if ProgressMax <> 0 then
    DownloadPage.SetProgress(Progress, ProgressMax)
  else
    DownloadPage.SetProgress(0, 0);
  Result := True;
end;

procedure InstallOllama;
var
  ResultCode: Integer;
  OllamaInstaller: String;
begin
  if IsOllamaInstalled then
  begin
    Log('Ollama already installed, skipping download');
    Exit;
  end;

  DownloadPage.Clear;
  DownloadPage.SetText('Downloading Ollama...', 'Please wait while Ollama is being downloaded.');
  DownloadPage.Show;

  try
    OllamaInstaller := ExpandConstant('{tmp}\OllamaSetup.exe');
    DownloadPage.Add(OLLAMA_INSTALLER_URL, 'OllamaSetup.exe', '');
    DownloadPage.Download;

    DownloadPage.SetText('Installing Ollama...', 'Please wait while Ollama is being installed.');
    DownloadPage.SetProgress(0, 0);
    Exec(OllamaInstaller, '/VERYSILENT /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

    if ResultCode <> 0 then
      MsgBox('Ollama installation returned a non-zero exit code. You may need to install Ollama manually.', mbError, MB_OK);
  finally
    DownloadPage.Hide;
  end;
end;

procedure DownloadDefaultModel;
var
  ResultCode: Integer;
  OllamaPath, Model: String;
begin
  OllamaPath := GetOllamaPath;
  if OllamaPath = '' then
  begin
    MsgBox('Could not find Ollama. Please install it manually and run: ollama pull ' + GetRecommendedModel, mbInformation, MB_OK);
    Exit;
  end;

  Model := GetRecommendedModel;
  if MsgBox(Format('Download AI model "%s"? This may take several minutes depending on your internet speed.', [Model]),
    mbConfirmation, MB_YESNO) = IDNO then
    Exit;

  WizardForm.StatusLabel.Caption := Format('Downloading AI model: %s (this may take a while)...', [Model]);
  Exec(OllamaPath, 'pull ' + Model, '', SW_SHOW, ewWaitUntilTerminated, ResultCode);

  if ResultCode <> 0 then
    MsgBox(Format('Model download may have failed. You can retry manually: ollama pull %s', [Model]), mbInformation, MB_OK)
  else
    WizardForm.StatusLabel.Caption := 'AI model downloaded successfully.';
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), @OnDownloadProgress);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    InstallOllama;
    DownloadDefaultModel;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('Remove application data (settings, cache, generated content)?', mbConfirmation, MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{localappdata}\travel-content-studio'), True, True, True);
      DelTree(ExpandConstant('{userappdata}\travel-content-studio'), True, True, True);
    end;
  end;
end;
