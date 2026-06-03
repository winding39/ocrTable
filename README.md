# OCR 表格识别（PyQt5 桌面版）

与 `whMoctcInput` 相同技术栈：PyQt5 + OpenCV 摄像头 + 阿里云百炼 OCR，识别表格后导出 xlsx。

## 功能

- 左侧：摄像头预览、拍照、多选导入图片
- 右侧：照片列表（仅显示文件名）、批量 OCR、实时日志、另存为 xlsx
- 系统设定：模型 API、可编辑提示词

## 安装

```bash
cd E:\python\cursor\ocrTable
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env` 填入 `VISION_API_KEY`，或在应用内「系统设定」配置。

## 运行

```bash
python main.py
```

（不再使用 `python app.py` / 浏览器）

## 目录

| 路径 | 说明 |
|------|------|
| `main.py` | PyQt5 入口 |
| `ui/` | 主窗口与页面 |
| `ocr/bailian.py` | 百炼 OCR |
| `utils/camera.py` | 摄像头 |
| `utils/excel_export.py` | xlsx 导出 |
| `data/images/` | 照片 |
| `data/exports/` | 生成的 xlsx |
| `logs/` | 运行与 OCR 日志 |
