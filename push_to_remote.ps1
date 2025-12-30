# Git 推送脚本
# 远程仓库: git@github.com:yzjjdcf/stake_code.git

Write-Host "🚀 开始设置 Git 远程仓库并推送代码..." -ForegroundColor Cyan

# 1. 检查并设置远程仓库
Write-Host "`n📡 设置远程仓库..." -ForegroundColor Yellow
$remoteUrl = "git@github.com:yzjjdcf/stake_code.git"

# 检查是否已有 origin
$existingRemote = git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "   更新现有的 origin 远程地址..." -ForegroundColor Gray
    git remote set-url origin $remoteUrl
} else {
    Write-Host "   添加新的 origin 远程地址..." -ForegroundColor Gray
    git remote add origin $remoteUrl
}

# 验证远程仓库
Write-Host "   验证远程仓库配置..." -ForegroundColor Gray
git remote -v

# 2. 创建新分支
Write-Host "`n🌿 创建新分支..." -ForegroundColor Yellow
$branchName = "feature/完善推送记录功能"
git checkout -b $branchName
if ($LASTEXITCODE -ne 0) {
    # 如果分支已存在，切换到该分支
    Write-Host "   分支已存在，切换到该分支..." -ForegroundColor Gray
    git checkout $branchName
}

# 3. 添加所有文件
Write-Host "`n📦 添加所有文件..." -ForegroundColor Yellow
git add -A

# 显示将要提交的文件
Write-Host "`n📋 将要提交的文件:" -ForegroundColor Cyan
git status --short

# 4. 提交
Write-Host "`n💾 提交更改..." -ForegroundColor Yellow
$commitMessage = "完善推送记录功能：添加代码状态、统计信息和金额显示，包含数据库文件"
git commit -m $commitMessage

if ($LASTEXITCODE -eq 0) {
    Write-Host "   ✅ 提交成功！" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  提交可能失败或没有更改需要提交" -ForegroundColor Yellow
}

# 5. 推送到远程
Write-Host "`n🚀 推送到远程仓库..." -ForegroundColor Yellow
git push -u origin $branchName

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ 完成！代码已推送到远程仓库" -ForegroundColor Green
    Write-Host "   远程地址: $remoteUrl" -ForegroundColor Cyan
    Write-Host "   分支: $branchName" -ForegroundColor Cyan
} else {
    Write-Host "`n❌ 推送失败，请检查网络连接和权限" -ForegroundColor Red
    Write-Host "   提示: 确保已配置 SSH 密钥或使用 HTTPS 地址" -ForegroundColor Yellow
}

