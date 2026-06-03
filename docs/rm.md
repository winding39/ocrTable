# 打包与部署指南

本文说明如何将「OCR 表格识别系统」（ocrTable）打包为 Windows 可执行程序，以及 `data/`、`.env` 等运行数据的存放位置。

## 与单文件打包的区别

若你熟悉旧项目 `bom_checker` 的单文件打包方式：

```powershell
.\.venv\Scripts\pyinstaller.exe -F -w --add-data "type_mapping.json;." bom_checker.py
```

本项目采用 **目录模式**（`ocrTable.spec`），原因如下：

| 对比项 | bom_checker（单文件 `-F`） | 本项目 ocrTable |
|--------|---------------------------|-----------------|
| 输出 | 单个 `.exe` | `dist/ocrTable/` 整个文件夹 |
| 规则/配置 | 打进 exe 或少量外挂 | `.env`、`data/app_settings.json` 放在 exe 旁边 |
| 运行数据 | 较少 | 拍照图片、导出 xlsx、历史、日志等需持久化 |
| 配置 | 界面可选外部 JSON | `.env` + 系统设定页写回 |

`data/` 中的图片、导出文件、`app_settings.json` 都是**运行时可写数据**，应放在 exe **旁边**，而不是打进 exe 内部。

## data/ 目录会创建在哪里？

打包后程序通过 `sys.executable` 定位根目录（见 `config.py`、`main.py`）：

```python
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)  # exe 所在目录
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
```

**结论：exe 放到哪里，`data/` 和 `logs/` 就在哪里。**

例如部署到 `D:\OCR表格识别\`：

```
D:\OCR表格识别\
├── ocrTable.exe
├── _internal\              ← PyQt5、OpenCV 等依赖（勿删）
├── 启动.bat                ← 可选，打包脚本会生成
├── .env                    ← API Key、摄像头等（需自行创建）
├── .env.example            ← 配置模板（打包后已复制）
├── data\
│   ├── app_settings.json   ← 系统设定保存（界面保存后生成）
│   ├── history.json        ← OCR 历史（运行时生成）
│   ├── images\             ← 拍照/导入原图，自动创建
│   └── exports\            ← 导出的 xlsx，自动创建
└── logs\
    ├── app.log
    ├── ocr_YYYY-MM-DD.log
    └── ai_prompts_YYYY-MM-DD.log
```

### data/ 各路径说明

| 路径 | 是否打进 exe | 说明 |
|------|-------------|------|
| `data/app_settings.json` | 否 | 模型、提示词、摄像头、分辨率等，系统设定保存后生成 |
| `data/history.json` | 否 | OCR 历史记录 |
| `data/images/` | 否 | 拍照/导入原图 |
| `data/exports/` | 否 | 识别结果 xlsx |
| `logs/` | 否 | 应用日志、OCR 流程日志、AI 提示词日志 |

## 配置在哪里？

1. **`.env`（主配置）**  
   - 放在 **exe 同目录**，`main.py` 启动时加载。  
   - 填写 `VISION_API_KEY`、模型名、`CAMERA_INDEX`、`CAPTURE_WIDTH` 等。  
   - 首次部署：将 `.env.example` 复制为 `.env` 并修改。

2. **界面「系统设定」**  
   - 模型、提示词、深度思考、摄像头、采集分辨率等保存到 `data/app_settings.json`，并可通过 `write_env_from_settings()` 同步到 `.env`。

## 打包前已做的代码适配

以下在 frozen 模式下已正确（无需再改即可打包）：

- **`config.py`**：`BASE_DIR` 使用 `sys.executable` 所在目录。  
- **`main.py`**：`.env` 路径基于 exe 目录加载。

未使用 `__file__` 作为数据根目录，避免 PyInstaller 临时目录导致数据丢失。

## 如何打包

### 环境要求

- Python 虚拟环境 `.venv`（项目根目录）。  
- 依赖：`pip install -r requirements.txt`  
- 打包工具：`pip install pyinstaller`

### 方式一：一键脚本（推荐）

在项目根目录 PowerShell 执行：

```powershell
cd e:\python\cursor\ocrTable
.\scripts\build_dist.ps1
```

脚本会执行 `pyinstaller -y ocrTable.spec`，并复制 `.env.example`、创建 `data/images`、`data/exports`、生成 `启动.bat`。

### 方式二：手动打包

```powershell
cd e:\python\cursor\ocrTable
.\.venv\Scripts\pyinstaller.exe -y ocrTable.spec
```

打包后整理分发文件：

```powershell
$Dist = "dist\ocrTable"
New-Item -ItemType Directory -Force -Path "$Dist\data\images", "$Dist\data\exports"
Copy-Item ".env.example" "$Dist\.env.example" -Force
```

重新打包时若提示输出目录非空，请加 `-y` 覆盖。

### 重要：必须运行 dist，不要运行 build

| 目录 | 能否直接运行 |
|------|-------------|
| **`dist\ocrTable\ocrTable.exe`** | 可以（含完整 `_internal`） |
| **`build\ocrTable\ocrTable.exe`** | **不能**（无完整 `_internal`，会报 Failed to load Python DLL） |

若报错路径含 `...\build\ocrTable\_internal\python313.dll`，说明点错了 exe。请只运行 **`dist\ocrTable\`** 下的程序，或双击 **`启动.bat`**。

## 部署给他人

1. 将整个 **`dist\ocrTable`** 文件夹复制到目标电脑（需包含 `_internal`）。  
2. 将 `.env.example` 复制为 **`.env`**，填写 `VISION_API_KEY` 等。  
3. 双击 **`ocrTable.exe`** 或 **`启动.bat`**。  
4. 首次运行会自动创建 `data/` 子目录与 `logs/`。  
5. 升级程序：保留 exe 同级的 `data/`、`.env`、`logs/`，用新版本覆盖 exe 与 `_internal` 即可。

## 以后重新打包

1. 关闭正在运行的旧 `ocrTable.exe`。  
2. 执行 `.\scripts\build_dist.ps1` 或 `pyinstaller -y ocrTable.spec`。  
3. 若用户已有旧部署，勿用开发机上的 `data/` 覆盖其生产数据；仅分发 exe + `_internal` + `.env.example`。

## 相关文件

| 文件 | 说明 |
|------|------|
| `ocrTable.spec` | PyInstaller 打包配置（目录模式、cv2、PyQt5 隐藏导入） |
| `scripts/build_dist.ps1` | 打包并整理 dist 的 PowerShell 脚本 |
| `config.py` | `BASE_DIR` 及 `data/`、`logs/` 路径 |
| `main.py` | 启动入口，加载 `.env` |
| `dist/ocrTable/` | 打包输出，可直接分发 |

## 常见问题

**Q：能否打成单个 exe（`-F`）？**  
A：可以但不推荐：体积大、启动慢，且 `data/` 持久化不便；当前目录模式便于备份与升级。

**Q：升级程序会丢数据吗？**  
A：不会。保留 exe 同级的 `data/`、`.env`、`logs/`，替换程序文件即可。

**Q：打包时出现 `tzdata` 警告？**  
A：Windows 上通常不影响；若 exe 无法启动，请查看 `logs/app.log` 或改用 `console=True` 临时打包排查。

**Q：摄像头在打包后无法打开？**  
A：在「系统设定 → 设备」中刷新摄像头列表并保存；确认本机已安装摄像头驱动，目录模式已包含 OpenCV DirectShow 后端。
