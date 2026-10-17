# 大会本地演示

## 在这台电脑打开

1. 双击后端文件夹的 `START-LOCAL-DEMO.bat`，演示期间保持窗口打开。
2. 后台：<http://127.0.0.1:18091/admin.html>
3. 官网：<http://127.0.0.1:18091/site/latest-events.html>

浏览器由你自行打开。若提示端口占用，先查看是否已有这份演示在运行；脚本不会停止其他程序。

本地数据存放在后端的 `instance-demo`，关闭／重启服务后保留。前后台由同一服务提供，运行时自动配置 API，不改团队的 `deployment.json` 或官网 `assets/config.js`。不需要服务器、域名或互联网；外部网站链接、在线地图和实时英文翻译仍依赖外部服务，不能据此承诺断网可用。

## 登录与演示步骤

迁入的实例沿用原本地演示账号。忘记密码时双击 `RESET-LOCAL-DEMO-PASSWORD.bat`，在终端自行输入两次新密码，至少 12 个字符；这只重设演示账号，不清空文章和图片，也不会更改 GitHub 密码。原会话将失效，重新登录即可。

建议演示：

1. 官网查看已准备的“职业分享会｜本地演示示例”。
2. 后台打开“活动与文章”，修改演示标题或正文，先预览。
3. 关闭预览；官网刷新仍应显示保存前的内容。
4. 点“保存并发布”，官网刷新显示新内容。图片上传后也需要保存。
5. 若展示草稿，新建演示文章后不勾“发布到网站”；预览可见，公开页面不可见。

当前日期字段是“发布日期”，不代表活动开始时间。样例明确标注演示用途，不是正式活动公告。未确认的小程序在导入的演示副本中隐藏；保留图片与原记录，没有删除公共资源。隐藏只控制前台展示，不是资料保密功能。

## 备份与恢复

演示前双击 `BACKUP-LOCAL-DEMO.bat`。完整备份位于 `demo-backups`，包括数据库、账号凭据和上传图片。目录已加入 Git 忽略；备份应私密保管，可复制到你自己的备用存储，**不要发到群里或上传 GitHub**。此入口保留全部既有备份。

恢复始终使用一个尚不存在的新目录，不覆盖当前演示。例如在后端目录的 PowerShell：

```powershell
.\.venv\Scripts\python.exe local_demo.py verify "备份压缩包的完整路径"
.\.venv\Scripts\python.exe local_demo.py restore "备份压缩包的完整路径" "instance-demo-recovered"
.\.venv\Scripts\python.exe local_demo.py --instance "instance-demo-recovered" serve --port 18093
```

恢复后的后台为 `http://127.0.0.1:18093/admin.html`，官网为 `http://127.0.0.1:18093/site/`，沿用备份内的演示账号。原演示目录保持原样。不要直接删除或覆盖当前实例来“恢复”。

## 换电脑或首次准备

需有 Python 依赖环境，以及相邻的 `MCSA-offical-website` 官网文件夹。Windows 的 Python 环境仍按仓库原说明准备；本次没有把 Python 安装包或 `.venv` 打包成便携程序。

- 已有完整备份：恢复到新电脑后端的 `instance-demo` 后运行启动入口。
- 导入既有本地实例：执行下面的命令；目标必须不存在。先建立完整备份，再复制数据，并仅在副本中隐藏名称含“小程序”的未确认条目，源实例不变。
- 全新演示：执行 `local_demo.py init`，在本机自行设置密码。它不会覆盖现有目录。

```powershell
.\.venv\Scripts\python.exe local_demo.py import-instance "原演示实例的完整路径"
.\.venv\Scripts\python.exe local_demo.py init
```

上面两条是两种准备方式，选一种。日常重启只运行 `START-LOCAL-DEMO.bat`，不要反复初始化。服务只监听 `127.0.0.1`；手机不能通过手机上的同一地址访问这台电脑，真机演示需另行安排。

实际大会电脑／投影、用户验收及成员的部门／地图／多语言交接仍需按实际范围确认。代码及本机检查完成不自动代表负责人已验收。
