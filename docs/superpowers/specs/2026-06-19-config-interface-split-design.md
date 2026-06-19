# 2026-06-19 大模型与飞书配置界面拆分及多模态适配设计规约 (Config Interface Split & Multimodal Integration Spec)

本设计文档旨在规约如何将大模型配置与飞书同步配置拆分为两个独立的全屏界面，同时在后端模型层引入动态大模型提供商（LLM Provider）分流机制，支持原生多模态能力，并支持在配置面板一键测试连接、获取模型列表及下拉切换。

---

## 1. 业务场景与诉求
*   **配置拆分**：将原来混合的系统配置弹窗彻底分离为“大模型 AI 引擎配置”与“飞书同步配置”两个独立的界面。
*   **全屏界面模式**：不再采用 Modal 弹窗，而是点击按钮后，将右侧主内容区（聊天画布）替换为全屏的配置界面，提供更宽阔空间。
*   **LobeChat 样式对齐**：大模型配置界面对齐 LobeChat 官方设计，使用垂直折叠面板（Accordion）列表来管理不同服务商，且支持单通道的延迟测试。
*   **一键获取模型列表**：在测试连接成功后，自动从大模型/中转代理的 `/v1/models` 接口获取可用的模型列表，前端“模型名称”表单将自动转换为下拉选择菜单（带自定义输入兜底）。
*   **多模态原生支持**：支持原生接入 Claude 和 Gemini 的多模态能力（如图片输入），不再强行使用 OpenAI 兼容层包装它们。

---

## 2. 详细设计规约

### 2.1 前端路由与视图管理 (Front-end View Management)
*   **Query State 控制**：使用 `nuqs` 管理 `view` 查询参数：
    *   `view=llm`：右侧主区域平滑切换为大模型配置页面。
    *   `view=feishu`：右侧主区域平滑切换为飞书与多维表格配置页面。
    *   其他/未设置：默认展示正常的聊天对话框。
*   **侧边栏（Sidebar）入口按钮**：在侧边栏顶部品牌区右侧，并排渲染两个小图标按钮：
    *   `Sparkles` (🤖) ➔ 点击触发 `setView('llm')`。
    *   `SlidersHorizontal` (⚙️) ➔ 点击触发 `setView('feishu')`。
*   **退出/切换机制**：在配置页面顶部提供一个“返回会话 ↩”按钮，点击后触发 `setView(null)`。同时，当用户点击侧边栏中的任何会话（Thread）或“新对话”按钮时，系统会自动重置 `view` 为 `null`，切回聊天视图。

### 2.2 前端配置页面 (Config Pages UI)
1.  **LlmConfigPage (大模型 AI 引擎配置)**
    *   **垂直手风琴面板 (Accordions)**：包括 DeepSeek、Kimi (Moonshot)、OpenAI (ChatGPT)、Anthropic Claude、Google Gemini 以及自定义代理（Custom Proxy）。
    *   **配置项展开**：点击某个面板可平滑展开，显式提供 API Key（可明密文切换）、Base URL、Model 名称等配置项。
    *   **延迟测试与模型获取**：每一个服务商面板内都有一个独立的“⚡ 测试连接”按钮，通过调用后端代理路由 `/api/config/test` 实时测试时延，测试成功后返回支持的 `models` 列表。
    *   **模型下拉选择菜单**：当获取到大模型提供商的可用模型列表后，原来的输入框将转换为下拉菜单。若接口未返回，则降级为手动输入框。
    *   **Provider 参数保存**：保存时，被设为 Primary Engine 的服务商对应的环境变量 `LLM_PROVIDER` 会写入 `.env`（其值对应为 `openai`、`anthropic` 或 `google_genai`）。同时，其他服务商已配的 Key 也会回写作为灾备缓存。

2.  **FeishuConfigPage (飞书与多维表格同步配置)**
    *   **纯净配置**：仅包含飞书 App ID、App Secret、Bitable App Token 以及 Bitable Table ID。
    *   物理移除所有大模型及备用灾备 Key 字段，消除逻辑重叠。

### 2.3 后端测试路由适配 (Connection Test Route)
重构 `web/src/app/api/config/test/route.ts` 以支持获取模型列表：
*   在测试 `/chat/completions` 通畅并计算延迟后，若成功，立即向目标 `baseUrl/models` 发送 GET 请求。
*   成功获取模型列表后，从返回的 `data` 中提取出 `id` 清单。
*   向前端返回 JSON：`{ ok: true, latency: number, models: string[] }`。

### 2.4 后端多模态模型层适配 (Back-end LLM Layer)
修改 `models.py` 的模型构造逻辑，从环境变量读取 `LLM_PROVIDER` 并执行动态实例化：
*   `LLM_PROVIDER="anthropic"` ➔ 从 `langchain_anthropic` 导入 `ChatAnthropic` 进行实例化。
*   `LLM_PROVIDER="google_genai"` ➔ 从 `langchain_google_genai` 导入 `ChatGoogleGenerativeAI` 进行实例化。
*   `LLM_PROVIDER="openai"` (默认) ➔ 依然使用 `init_chat_model(..., model_provider="openai")`。

```python
def _build_chat_model(model_id: str, base_url: str, api_key: str, provider: str = "openai") -> BaseChatModel:
    """根据 provider 动态构造对应的原生多模态模型实例"""
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model_id, api_key=api_key, temperature=0.7, timeout=60)
    elif provider == "google_genai":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model_id, api_key=api_key, temperature=0.7, timeout=60)
    else:
        return init_chat_model(
            model=model_id,
            model_provider="openai",
            base_url=base_url,
            api_key=api_key,
            temperature=0.7,
            timeout=60,
        )
```

---

## 3. 验证与上线计划
1.  **编译与类型检查**：在前端 `web/` 执行 `npx tsc --noEmit`，确保无变量未定义或 TS 类型报错。
2.  **单元与集成测试**：
    *   在前端保存大模型配置为 Anthropic/Gemini，确认配置文件 `.env` 被正确写入且 Python 侧正常加载原生模型。
    *   在前端会话中上传图片测试，确保多模态调用不会因兼容层报错。
3.  **远程服务器自动部署**：执行 `uv run python tools/deploy.py`，部署至远程腾讯云并重启 PM2 服务，验证界面与功能工作正常。
