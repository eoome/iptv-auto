# IPTV 直播源自动更新

📺 自动从多个 GitHub 开源 IPTV 项目抓取直播源，定时验证可用性，生成 IPv4/IPv6 播放列表。

## ✨ 功能

- 🔄 **每 6 小时自动更新** — GitHub Actions 定时运行
- ✅ **自动验证** — 多线程检测源的可用性，剔除失效链接
- 🌐 **IPv4 + IPv6 双栈** — 分别生成两种格式的播放列表
- 📺 **自动分类** — 央视、卫视、地方、港澳台等自动归类
- 🌍 **GitHub Pages 网页** — 美观的频道展示页面，支持搜索和复制

## 📋 数据来源

从以下 GitHub 开源项目自动抓取（可在 `scripts/sources.json` 中添加更多）：

- [vbskycn/iptv](https://github.com/vbskycn/iptv)
- [YueChan/IPTV](https://github.com/YueChan/IPTV)
- [fanmingming/live](https://github.com/fanmingming/live)
- [HerbertHe/iptv-resources](https://github.com/HerbertHe/iptv-resources)

## 🚀 快速开始

### 1. Fork 或创建仓库

```bash
# 创建新仓库后 clone
git clone https://github.com/你的用户名/iptv-auto.git
cd iptv-auto
```

### 2. 推送到 GitHub

```bash
git add .
git commit -m "init: IPTV auto-updater"
git push origin main
```

### 3. 开启 GitHub Pages

进入仓库 → Settings → Pages → Source 选 `gh-pages` 分支（或 `docs/` 目录）

### 4. 手动触发首次运行

进入仓库 → Actions → "Update IPTV Sources" → Run workflow

等待几分钟，首次运行完成后即可访问你的 GitHub Pages 网页。

## 📂 文件结构

```
├── .github/workflows/
│   └── update.yml          # GitHub Actions 工作流
├── scripts/
│   ├── sources.json        # 上游源配置
│   └── update.py           # 主脚本
├── tv/
│   ├── iptv4.txt           # IPv4 TXT 格式
│   ├── iptv4.m3u           # IPv4 M3U 格式
│   ├── iptv6.txt           # IPv6 TXT 格式
│   └── iptv6.m3u           # IPv6 M3U 格式
├── docs/
│   ├── index.html           # 展示网页
│   └── channels*.json       # 频道数据
└── README.md
```

## 🔧 添加更多源

编辑 `scripts/sources.json`，在 `upstream` 数组中添加：

```json
{
  "name": "某IPTV项目",
  "urls": [
    "https://raw.githubusercontent.com/用户名/仓库名/分支/文件路径.txt"
  ]
}
```

支持 TXT 和 M3U 两种格式，会自动识别。

## 📺 使用方法

### 播放器导入

复制以下链接之一，粘贴到支持 IPTV 的播放器中：

- **TXT 格式：** `https://你的用户名.github.io/iptv-auto/tv/iptv4.txt`
- **M3U 格式：** `https://你的用户名.github.io/iptv-auto/tv/iptv4.m3u`
- **IPv6：** 把 `iptv4` 换成 `iptv6`

### 推荐播放器

| 平台 | 播放器 |
|------|--------|
| Android TV | TVBox、影视仓、Televio |
| 手机 | IPTV Pro、OPlayer |
| 电脑 | VLC、PotPlayer |
| iOS | Cloud Stream IPTV |

## ⚠️ 免责声明

- 本项目仅供学习研究用途
- 所有直播源来自互联网公开资源，不保证可用性和合法性
- 请于下载后 24 小时内删除
- 如有侵权，请联系删除

## 📄 License

MIT
