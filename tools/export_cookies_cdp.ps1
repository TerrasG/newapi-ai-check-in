# 从 CDP (http://127.0.0.1:9222) 导出全部 cookie，组装成 playwright storage state
# 用法: pwsh -NoProfile -File tools\export_cookies_cdp.ps1
$ErrorActionPreference = 'Stop'

function Get-CDPTabs {
    $tabs = Invoke-RestMethod -Uri 'http://127.0.0.1:9222/json' -Method Get
    # 找到非扩展、非内部页面
    return $tabs | Where-Object { $_.type -eq 'page' -and $_.url -notlike 'chrome://*' -and $_.url -notlike '*chrome-extension://*' }
}

function Send-CDP {
    param([int]$Id, [string]$Method, $Params)
    # 复用 WebSocket 太复杂，这里用 /json/version 拿 webSocketDebuggerUrl 走单次调用不现实
    # 改用：直接通过 Runtime.evaluate 在页面上下文里读 document.cookie 不可取（HttpOnly）
    # 正确方式：Network.getAllCookies 需要 WebSocket。这里用 PowerShell WebSocket 客户端。
}

# 使用 System.Net.WebSockets 实现 CDP Network.getAllCookies
function Get-AllCookiesViaCDP {
    param([string]$WsUrl)
    $ws = [System.Net.WebSockets.ClientWebSocket]::new()
    $cts = [System.Threading.CancellationTokenSource]::new()
    [void]$ws.ConnectAsync([Uri]$WsUrl, $cts.Token).GetResult()

    $id = 1
    $msg = @{ id = $id; method = 'Network.enable' } | ConvertTo-Json -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($msg)
    $seg = [ArraySegment[byte]]::new($bytes)
    [void]$ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cts.Token).GetResult()

    # 等待 enable 响应
    $buf = New-Object byte[] 65536
    $res = $ws.ReceiveAsync([ArraySegment[byte]]::new($buf), $cts.Token).GetResult()
    $respText = [Text.Encoding]::UTF8.GetString($buf, 0, $res.Count)

    # 发送 Network.getAllCookies
    $id = 2
    $msg = @{ id = $id; method = 'Network.getAllCookies' } | ConvertTo-Json -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($msg)
    $seg = [ArraySegment[byte]]::new($bytes)
    [void]$ws.SendAsync($seg, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cts.Token).GetResult()

    # 读响应直到拿到 id=2
    $result = $null
    while ($null -eq $result) {
        $res = $ws.ReceiveAsync([ArraySegment[byte]]::new($buf), $cts.Token).GetResult()
        $respText = [Text.Encoding]::UTF8.GetString($buf, 0, $res.Count)
        $obj = $respText | ConvertFrom-Json
        if ($obj.id -eq 2) {
            $result = $obj.result
        }
    }
    $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, 'done', $cts.Token).GetResult()
    return $result
}

# 主流程
$tabs = Get-CDPTabs
if (-not $tabs) {
    Write-Error '没有可用的页面标签页，请确认 Chrome 调试端口已开且有页面'
    exit 1
}
$wsUrl = $tabs[0].webSocketDebuggerUrl
Write-Host "连接: $wsUrl"

$cookies = Get-AllCookiesViaCDP -WsUrl $wsUrl

if (-not $cookies -or -not $cookies.cookies) {
    Write-Error '未获取到 cookie'
    exit 1
}

$all = $cookies.cookies
Write-Host "共获取 $($all.Count) 个 cookie"
# 只保留 linux.do / connect.linux.do 相关的
$relevant = $all | Where-Object { $_.domain -like '*linux.do*' -or $_.domain -like '*connect.linux.do*' }
Write-Host "其中 linux.do 相关: $($relevant.Count)"
$relevant | ForEach-Object { Write-Host ("  {0} {1} (len={2})" -f $_.domain, $_.name, ($_.value | Measure-Object -Character | Select-Object -ExpandProperty Characters)) }

# 组装 playwright storage_state 格式
$storageState = @{
    cookies = @($all | ForEach-Object {
        @{
            name = $_.name
            value = $_.value
            domain = $_.domain
            path = $_.path
            expires = [int]$_.expires
            httpOnly = $_.httpOnly
            secure = $_.secure
            sameSite = switch ($_.sameSite) {
                'Lax'   { 'Lax' }
                'Strict'{ 'Strict' }
                default { 'None' }
            }
        }
    })
    origins = @()
}

$outPath = Join-Path $PSScriptRoot '..' 'storage-states' 'linuxdo_storage_state.json'
$outPath = [IO.Path]::GetFullPath($outPath)
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($outPath)) | Out-Null
$storageState | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $outPath -Encoding utf8
Write-Host "✅ storage state 已保存: $outPath"
Write-Host "   cookie 数: $($storageState.cookies.Count)"
