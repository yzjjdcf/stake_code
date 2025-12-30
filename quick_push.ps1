# 快速推送脚本 - 使用绕过执行策略的方式运行
# 使用方法: powershell -ExecutionPolicy Bypass -File .\quick_push.ps1

Write-Host "🚀 开始推送代码到远程仓库..." -ForegroundColor Cyan

# 设置远程仓库
$remoteUrl = "git@github.com:yzjjdcf/stake_code.git"
Write-Host "`n📡 设置远程仓库: $remoteUrl" -ForegroundColor Yellow

$existingRemote = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0) {
    git remote set-url origin $remoteUrl
    Write-Host "   ✅ 已更新远程地址" -ForegroundColor Green
} else {
    git remote add origin $remoteUrl
    Write-Host "   ✅ 已添加远程地址" -ForegroundColor Green
}

# 创建分支
$branchName = "feature/完善推送记录功能"
Write-Host "`n🌿 创建/切换到分支: $branchName" -ForegroundColor Yellow
git checkout -b $branchName 2>$null
if ($LASTEXITCODE -ne 0) {
    git checkout $branchName
}

# 添加文件
Write-Host "`n📦 添加所有文件..." -ForegroundColor Yellow
git add -A

# 提交
Write-Host "`n💾 提交更改..." -ForegroundColor Yellow
git commit -m "完善推送记录功能：添加代码状态、统计信息和金额显示，包含数据库文件"

# 推送
Write-Host "`n🚀 推送到远程..." -ForegroundColor Yellow
git push -u origin $branchName

Write-Host "`n✅ 完成！" -ForegroundColor Green

