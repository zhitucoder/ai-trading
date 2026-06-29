# VSCode 安装指南

## 下载

前往官网下载对应系统的安装包：

> https://code.visualstudio.com/

页面会自动识别你的操作系统，点击蓝色的 **Download** 按钮即可。

> 如果浏览器没有自动下载，手动选择你的平台：Windows / macOS / Linux。

---

## Windows 安装

1. 双击下载的 `VSCodeSetup-xxx.exe` 安装文件
2. 一路点 **下一步（Next）**，**不需要改任何设置**
3. 关键一步：在"选择附加任务"页面，**勾选以下两项**：
   - ☑ 添加到上下文菜单（通过"Code"打开）
   - ☑ 将"Code"注册为受支持的文件类型的编辑器
4. 点击 **安装（Install）** 完成

安装完成后桌面会出现 VSCode 图标，双击打开即可。

---

## macOS 安装

1. 双击下载的 `.zip` 压缩包，系统会自动解压出 `Visual Studio Code.app`
2. 将 `Visual Studio Code.app` 拖到 **Applications（应用程序）** 文件夹
3. 首次打开时，如果系统提示"无法验证开发者"，去 **系统设置 → 隐私与安全性**，页面下方会有"仍要打开"的提示，点击即可
4. （推荐）打开 VSCode，按 `Cmd+Shift+P` 打开命令面板，输入 `shell command`，选择 **Install 'code' command in PATH**，这样以后在终端里输入 `code .` 就能直接用 VSCode 打开当前目录

---

## 验证安装

安装完成后，打开终端（或 CMD），输入：

```bash
code --version
```

如果能显示版本号（例如 `1.98.0`），就说明安装成功了。

---

## 首次启动建议

1. 打开 VSCode
2. 左侧点击 **Extensions** 图标（或按 `Ctrl+Shift+X`）
3. 搜索并安装 **Chinese (Simplified) 中文简体语言包**，安装后重启即可看到中文界面
4. 后续在本课程中还会安装 Claude Code / OpenCode 插件

---

## 常见问题

**Q：安装后打不开，没反应？**
A：可能是系统权限问题。Windows 尝试右键 → 以管理员身份运行；macOS 检查"隐私与安全性"是否拦截了应用。

**Q：`code` 命令找不到？**
A：Windows 重启终端即可；macOS 需要手动安装 shell 命令（见上方 macOS 说明）；WSL 确认已安装 Remote - WSL 插件。

**Q：VSCode 是免费的吗？**
A：完全免费，微软官方提供，无任何付费功能。
