# PowerShell 脚本：备份数据库文件
# 使用方法: .\backup_database.ps1 [目标路径]

param(
    [string]$TargetPath = "backups"
)

$dbFile = "db.sqlite3"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupFile = "$TargetPath\db_backup_$timestamp.sqlite3"

# 创建备份目录
if (-not (Test-Path $TargetPath)) {
    New-Item -ItemType Directory -Path $TargetPath | Out-Null
}

# 检查数据库文件是否存在
if (-not (Test-Path $dbFile)) {
    Write-Host "❌ 数据库文件不存在: $dbFile" -ForegroundColor Red
    exit 1
}

# 复制数据库文件
try {
    Copy-Item $dbFile $backupFile -Force
    $fileSize = (Get-Item $backupFile).Length / 1KB
    Write-Host "✅ 备份成功！" -ForegroundColor Green
    Write-Host "   文件: $backupFile" -ForegroundColor Cyan
    Write-Host "   大小: $([math]::Round($fileSize, 2)) KB" -ForegroundColor Cyan
} catch {
    Write-Host "❌ 备份失败: $_" -ForegroundColor Red
    exit 1
}

