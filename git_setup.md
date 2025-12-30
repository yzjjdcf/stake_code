# Git 远程仓库设置指南

## 1. 查看当前远程仓库

```powershell
git remote -v
```

## 2. 添加新的远程仓库

如果还没有添加远程仓库：

```powershell
# 添加新的远程仓库（替换为你的实际地址）
git remote add origin <你的远程仓库地址>

# 例如：
# git remote add origin https://github.com/username/repo.git
# 或
# git remote add origin git@github.com:username/repo.git
```

如果已经有 origin，可以更新或添加新的：

```powershell
# 更新现有的 origin
git remote set-url origin <新的远程仓库地址>

# 或添加一个新的远程（使用不同的名称）
git remote add new-origin <新的远程仓库地址>
```

## 3. 创建新分支并推送

```powershell
# 创建并切换到新分支
git checkout -b feature/完善推送记录功能

# 添加所有文件
git add -A

# 提交
git commit -m "完善推送记录功能：添加代码状态、统计信息和金额显示，包含数据库文件"

# 推送到远程新分支
git push -u origin feature/完善推送记录功能
```

## 4. 或者推送到主分支

```powershell
# 如果推送到主分支（main 或 master）
git push -u origin main
# 或
git push -u origin master
```

## 5. 完整流程示例

```powershell
# 1. 添加远程仓库
git remote add origin <你的远程仓库地址>

# 2. 创建新分支
git checkout -b feature/完善推送记录功能

# 3. 添加所有文件
git add -A

# 4. 查看状态
git status

# 5. 提交
git commit -m "完善推送记录功能：添加代码状态、统计信息和金额显示，包含数据库文件"

# 6. 推送到远程
git push -u origin feature/完善推送记录功能
```

