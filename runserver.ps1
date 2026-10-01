param(
    [string]$Address = '127.0.0.1:8000',
    [string]$SshTarget = 'root@82.25.66.238',
    [string]$DbContainer = 'plataforma_sobreposicao-postgis-1'
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$tunnel = $null

function Test-DatabasePort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $pending = $client.ConnectAsync('127.0.0.1', 5433)
        return ($pending.Wait(500) -and $client.Connected)
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

try {
    if (-not (Test-Path -LiteralPath $python)) {
        throw 'Ambiente .venv nao encontrado. Configure as dependencias antes de iniciar.'
    }

    if (-not (Test-DatabasePort)) {
        # O banco com os dados e o container `postgis` (sem porta publicada);
        # a porta 5433 do servidor e o banco antigo, vazio. O IP do container
        # muda quando ele e recriado, entao e consultado a cada inicio.
        $dbHost = (& ssh.exe -o BatchMode=yes -o ConnectTimeout=10 $SshTarget `
            "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' $DbContainer" |
            Out-String).Trim().Split(' ')[0]
        if (-not $dbHost) { throw "Nao foi possivel obter o IP do container $DbContainer no servidor." }

        Write-Host "Abrindo tunel SSH para o banco ($DbContainer em $dbHost) na porta local 5433..."
        $tunnel = Start-Process -FilePath 'ssh.exe' -WindowStyle Hidden -PassThru -ArgumentList @(
            '-N', '-T', '-o', 'BatchMode=yes',
            '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=10',
            '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
            '-L', "127.0.0.1:5433:${dbHost}:5432", $SshTarget
        )
        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            if ($tunnel.HasExited) { throw 'O tunel SSH encerrou. Verifique sua chave SSH e o acesso ao servidor.' }
            if (Test-DatabasePort) { $ready = $true; break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $ready) { throw 'Nao foi possivel conectar ao banco pela porta 5433.' }
    }

    Write-Host "Iniciando Django em http://$Address/ (Ctrl+C para encerrar)."
    & $python -u manage.py runserver $Address
    if ($LASTEXITCODE -ne 0) { throw "Django encerrou com codigo $LASTEXITCODE." }
} finally {
    if ($null -ne $tunnel -and -not $tunnel.HasExited) {
        Stop-Process -Id $tunnel.Id
    }
}
