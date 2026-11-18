# serve.ps1 - Static localhost server for the ETF Dashboard (no Python required).
# Usage: powershell -ExecutionPolicy Bypass -File serve.ps1 [-Port 5000]
# Note: /api/* refresh endpoints need Python + server.py; they return 501 here.
param([int]$Port = 5000)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$detailsUrl = 'https://gjpjhslkxdkxffeipumh.supabase.co/storage/v1/object/public/site-data/details'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$mime = @{
    '.html' = 'text/html; charset=utf-8'; '.js' = 'application/javascript; charset=utf-8'
    '.css' = 'text/css; charset=utf-8'; '.json' = 'application/json; charset=utf-8'
    '.png' = 'image/png'; '.jpg' = 'image/jpeg'; '.jpeg' = 'image/jpeg'
    '.svg' = 'image/svg+xml'; '.ico' = 'image/x-icon'; '.toml' = 'text/plain'
}

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
$listener.Start()
Write-Host "Armstrong Capital - ETF Dashboard"
Write-Host "Serving $root"
Write-Host "Open: http://localhost:$Port   (Ctrl+C to stop)"

try {
    while ($listener.IsListening) {
        $ctx = $listener.GetContext()
        $res = $ctx.Response
        try {
            $path = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath).TrimStart('/')
            if ($path -eq '') { $path = 'index.html' }
            $file = [IO.Path]::GetFullPath((Join-Path $root $path))

            if ($path.StartsWith('api/')) {
                $res.StatusCode = 501
                $bytes = [Text.Encoding]::UTF8.GetBytes('{"status":"error","message":"Refresh requires Python server (server.py)"}')
                $res.ContentType = 'application/json'
            } elseif ($path.StartsWith('details/') -and -not (Test-Path $file -PathType Leaf)) {
                # Mirror netlify.toml: per-ETF composition lives in the PUBLIC Supabase bucket (no token).
                try {
                    $wc = New-Object System.Net.WebClient
                    $bytes = $wc.DownloadData("$detailsUrl/" + $path.Substring(8))
                    $res.ContentType = 'application/json; charset=utf-8'
                    $res.AddHeader('Cache-Control', 'no-cache')
                } catch {
                    $res.StatusCode = 404
                    $bytes = [Text.Encoding]::UTF8.GetBytes('Not found')
                }
            } elseif ($file.StartsWith($root) -and (Test-Path $file -PathType Leaf)) {
                $bytes = [IO.File]::ReadAllBytes($file)
                $ext = [IO.Path]::GetExtension($file).ToLower()
                $res.ContentType = if ($mime.ContainsKey($ext)) { $mime[$ext] } else { 'application/octet-stream' }
                $res.AddHeader('Cache-Control', 'no-cache')
            } else {
                $res.StatusCode = 404
                $bytes = [Text.Encoding]::UTF8.GetBytes('Not found')
            }
            Write-Host "$($ctx.Request.HttpMethod) /$path -> $($res.StatusCode)"
            $res.ContentLength64 = $bytes.Length
            $res.OutputStream.Write($bytes, 0, $bytes.Length)
        } catch {
            Write-Host "Error: $_"
        } finally {
            $res.Close()
        }
    }
} finally {
    $listener.Stop()
}
