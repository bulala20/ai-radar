# DeepSeek V4.1 Flash 新版本：许愿式编程一键成真

> 等级：S · 频道：自媒体与个人成长 · 来源：人人都是产品经理

## 摘要

DeepSeek V4.1 Flash 更新至 1017 版本，性能与成本实现帕累托改进，任务运行时间与输出长度同步缩短。从零构建 3D 建模、游戏开发等完整项目的能力显著增强，自研搜索 API 也正式对外开放。本文拆解这次更新背后的产品逻辑与生态野心。 DeepSeek V4.1 Flash 现已更新至 V4.1-Flash-1017 版本，官方网页端、APP 与 API 模型已同步变更为新模型。 性能–费用的帕累托改进 相比上一版本的 DeepSeek V4.1 Flash，新模型在各方面的基准测试中取得了长足的提升。 在提升性能的同时，我们还缩短了模型的任务运行时间与输出长度，让用户能够以更低成本、更快速度完成任务（如下图所示），在多个 Harness 下达到了新的性能-费用帕累托最优。特别地，本次我们着重针对 DeepSeek Harness、腾讯 CodeBuddy、WorkBuddy 等平台框架进行了优化。请升级到 DeepSeek Harness 0.2.1-rc.1 及以上版本，以获得适配新版模型的最优体验。 DeepSeek V4.1 Flash 1017 使用 mini-swe-v2 框架测试 DeepSWE 的性能/成本图 从零开始的完整项目开发 DeepSeek V4.1 Flash 1017 通过基于自反馈的强化学习（RL）训练技术，提升了在游戏开发、3D 建模等方面从零开始构建完整项目的能力，能够支持实现更多“许愿式”编程任务及项目开发请求。以下案例展示了新版本模型在较少的提示词与素材参考条件下，在 DeepSeek Harness 框架环境内通过极短的交互轮次直接实现的项目效果： 示例1：故宫 3D 建模展示效果 示例2：网页版赛车游戏开发效果 示例3：基于 godot 引擎开发的《传送门2》游戏复刻效果 示例4：Valley of Ages-以 3D 场景动态展现从史前时代到现代的发展历程 开放自研搜索 API 长期以来，DeepSeek 网页端与 API 端的搜索能力均由自研 DeepSeek 搜索引擎提供底层支持，稳定处理每天来自全球各地的数亿次搜索请求。 DeepSeek 搜索是 AI 原生的通用搜索引擎，索引了全球千亿级网页，支持多语言搜索，实时返回高相关、高权威、高时效的优质结果。针对 SEO 作弊、GEO 操纵和低质 AIGC，我们通过严格的识别机制对其进行过滤，确保向用户与 LLM 呈现权威可信的信息。 本次新版本发布 DeepSeek API 新增对 Search 与 Fetch 接口的支持，相关能力正式向公众开放。两个接口价格均为 5 元 / 千次，详细使用方法请参考官方 API 文档：API 指南 &#8211; 网页搜索与抓取。 请注意，当前用户在 DeepSeek Harness / Claude Code / Codex 中使用 DeepSeek API 时，已经会通过 Server 端工具调用访问到 Search/Fetch 接口，这部分 Search/Fetch 接口调用目前未计费，并将在两周后（北京时间 2026 年 11 月 1 日 00:00）开始按次收取调用费用。 模型开源 DeepSeek-V4.1-Flash-1017 模型权重下载地址如下： HuggingFace: https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017 ModelScope: https://modelscope.cn/models/deepseek-ai/DeepSeek-V4.1-Flash-1017 作者：DeepSeek 来源公众号：DeepSeek 题图来自Unsplash，基于CC0协议

## 评级理由



来源：DeepSeek V4.1 Flash 新版本：许愿式编程一键成真 https://www.woshipm.com/ai/6480049.html
