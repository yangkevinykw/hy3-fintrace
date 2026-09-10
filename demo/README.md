# FinTrace 演示视频

[播放 MP4 演示视频](fintrace-demo.mp4)

实际本地工作台录屏，含中文旁白和画面说明。覆盖八个章节：项目介绍、答案与过程独立判定、证据定位、修改重评、三组批量对照、AI 复核争议、真实 Hy3 解答回放、项目入口。

本片回放已保存的实验结果，没有新增模型调用或提交复核记录。画面中的章节提示和高亮为演示辅助；题目、计算步骤和评估结果来自实际应用。

- `fintrace-demo.mp4`：H.264 / AAC 视频。
- `poster.png`：工作台预览。
- `fintrace-demo.srt`：中文旁白字幕。
- `transcript.md`：旁白全文。
- `scenes.json`：录制章节与说明。

## 重录

录制工具独立于项目运行依赖。需要 Node.js Playwright / Chromium、Windows 中文语音；视频使用浏览器自带的 MP4 编码器合成。

先启动本地工作台，依次运行 `scripts/prepare_demo.ps1`、`node scripts/record_demo.cjs`、`node scripts/mux_demo.cjs`、`python -X utf8 scripts/build_demo.py`。必要时用 `NODE_PATH` 指向 Playwright 包目录、`DEMO_CHROMIUM` 指向 Chromium 可执行文件。旁白使用本机中文语音离线合成。

`.work` 中的原始录屏与 WAV 文件仅用于制作，不进入版本库。
