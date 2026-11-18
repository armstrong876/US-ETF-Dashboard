# serve-live.ps1 - Localhost preview that shows the SAME data as the live site.
# Usage: powershell -ExecutionPolicy Bypass -File serve-live.ps1 [-Port 5000]
# Pages/code (html, js, css, images) come from THIS folder, so your local edits show up.
# Data files are read live from the PUBLIC Supabase bucket, mirroring netlify.toml.
# Read-only: it only downloads public files. No keys, no uploads, no deploys.
# /api/* endpoints return 501 here (they need server.py, which can deploy - not used).
param([int]$Port = 5000)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$siteData = 'https://gjpjhslkxdkxffeipumh.supabase.co/storage/v1/object/public/site-data'
$liveFiles = @('dashboard.json', 'dashboard_all.json', 'etf_analytics.json', 'etf_detail_data.json', 'history.json')
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
Write-Host "Armstrong Capital - ETF Dashboard (LIVE data preview)"
Write-Host "Serving $root"
Write-Host "Open: http://localhost:$Port   (Ctrl+C to stop)"

try {
    while ($listener.IsListening) {
        $ctx = $listener.GetContext()
        $res = $ctx.Response
        $note = ''
        try {
            $path = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath).TrimStart('/')
            if ($path -eq '') { $path = 'index.html' }
            $file = [IO.Path]::GetFullPath((Join-Path $root $path))

            if ($path.StartsWith('api/')) {
                $res.StatusCode = 501
                $bytes = [Text.Encoding]::UTF8.GetBytes('{"status":"error","message":"Refresh requires Python server (server.py)"}')
                $res.ContentType = 'application/json'
            } elseif ($liveFiles -contains $path -or $path.StartsWith('details/')) {
                # Live data from the public Supabase bucket (same as the Netlify site).
                try {
                    $wc = New-Object System.Net.WebClient
                    $bytes = $wc.DownloadData("$siteData/$path")
                    $res.ContentType = 'application/json; charset=utf-8'
                    $res.AddHeader('Cache-Control', 'no-cache')
                    $note = ' (live)'
                } catch {
                    if (Test-Path $file -PathType Leaf) {
                        # Offline fallback: old local copy, clearly flagged in the console.
                        $bytes = [IO.File]::ReadAllBytes($file)
                        $res.ContentType = 'application/json; charset=utf-8'
                        $note = ' (LIVE FAILED - showing OLD local copy)'
                    } else {
                        $res.StatusCode = 404
                        $bytes = [Text.Encoding]::UTF8.GetBytes('Not found')
                    }
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
            Write-Host "$($ctx.Request.HttpMethod) /$path -> $($res.StatusCode)$note"
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
