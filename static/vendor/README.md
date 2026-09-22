# 前端依赖

以下两个依赖的固定版本发布文件随项目提供，无需构建或从 CDN 加载。页面的 Tailwind 和字体仍使用 CDN。更新这两个依赖时，从 npm 对应版本 tarball 提取并校验 registry 的 SHA-512 integrity，保留各自许可证。

- [streaming-markdown](https://github.com/thetarnav/streaming-markdown) **0.2.15**, MIT：`smd.js` → `streaming-markdown.js`。应用层在 `js/chat/markdown.js` 中限制链接协议；不修改上游解析器。
- [eventsource-parser](https://github.com/rexxars/eventsource-parser) **4.1.1**, MIT：`dist/{index,parse,errors}.js` → `eventsource-parser/`。
