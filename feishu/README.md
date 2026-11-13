# 飞书机器人（独立可选模块）

通过飞书自建应用接收词表 PDF，自动生成短文，并**回发一个自包含离线 HTML 文件**（音频 base64 内嵌，单文件即可离线查看 + 播放）。

> 本模块独立于网页服务。不装 `lark-oapi`、不配飞书应用，核心与网页功能不受影响。

## 安装

```bash
pip install -r feishu/requirements.txt   # lark-oapi
```

## 飞书应用配置

1. 在 [飞书开放平台](https://open.feishu.cn/) 创建**企业自建应用**，获取 `App ID` / `App Secret`。
2. 开启**机器人**能力。
3. 订阅事件：`im.message.receive_v1`（接收消息）。
4. 事件订阅方式选 **长连接（WebSocket）**——本模块用 `lark.ws.Client`，无需公网回调地址。
5. 权限：`im:message`、`im:message:send_as_bot`、`im:resource`（下载用户上传文件）、`im:file`（上传回发文件）。
6. 发布应用版本，管理员审批通过后在飞书内添加该机器人。

## 配置密钥

```bash
cp feishu_config.example.json feishu_config.json
# 编辑 feishu_config.json, 填入 app_id / app_secret
```

> `feishu_config.json` 已被 `.gitignore` 忽略，**切勿提交真实密钥**。

## 启动

```bash
cd feishu
python feishu_bot.py
# 看到 "飞书机器人已启动, 等待消息..." 即成功连上 WebSocket
```

## 使用

- **发 PDF 文件**给机器人 → 自动生成 → 回发离线 HTML 文件。
- **发纯文本** → 机器人提示"请直接发送当日的单词 PDF 文件"。
  若存在 `pending_doc.json`（外部脚本预置的待投递文件），发任意文本即触发投递。

## 与网页模块联动

生成物默认写入 `../webapp/generated/`，并登记到 `../webapp/index.json`。
若同时运行网页服务（`webapp/server.py`），飞书生成的短文会出现在网页历史列表中。
不运行网页服务也不影响飞书收发。

## 备选：飞书云文档

`feishu_doc.py` 提供另一种投递方式——把短文写入**飞书云文档**（飞书内直接阅读，无需下载文件）。
可作为 `feishu_bot.py` 中 `send_file` 的替代方案调用，需额外权限 `docx:document`、`drive:permission`。
