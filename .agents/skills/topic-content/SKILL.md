---
name: topic-content
description: 根据一个内容方向(如露营装备、亲子出游、护肤),从飞书爆款数据中提炼选题并产出小红书文案。当用户给出一个主题/方向、或要求"出选题""写小红书文案""按某方向创作"时使用。
---

# 按方向产出选题 + 文案

这是一个两步式工作流:先给选题菜单,用户选定后再写完整文案。

## 检索与取证

检索顺序、mode 处理、轻/重委派、时效防伪一律遵循**主控 system prompt §6《检索与证据规约》**,本技能不重述。要点:语义优先检索 Postgres 底座→必要时关键词补召→精读 top-N→按需 `graph_expand`;数据不足时明说"当前数据不足"、建议同步飞书,不编造、不拿弱相关凑依据。

## 第一步:出选题(用户给方向后)

1. 按 §6 检索取证,记录实际采用来源的 `resource_id`、标题、依据摘要、`source_updated_at`、`indexed_at`(任一未知写"未知")。
2. 需要精读大量全文或跨多源综合时,用 `task` 委派 `knowledge-atom-retriever` 返回证据包;分析结论保留在当前上下文,不通过文件传递。
3. 基于分析,产出 **3~5 个选题方向**,按 system prompt「输出协议」里 `xhs_topics` 代码块格式输出
   (前端据此渲染可点选卡片)。intro 写一句引导语,topics 每项是"一句话角度（预期爆点）",
   evidence 只列实际采用的来源。
   最终回复用户前先调用 `save_generated_topic` 保存 direction、topics 和实际 evidence,再调用 `sync_topic_to_feishu` 同步飞书;数据库成功而飞书失败时保留数据库记录并明确提示同步失败。
4. **停下,请用户选择一个选题。不要在这一步直接写完整文案。**

## 第二步:写文案(用户选定选题后)

为选定选题写完整小红书文案,按 system prompt「输出协议」里 `xhs_copy` 代码块格式输出
(前端据此渲染带一键复制的文案卡)。evidence 只列实际采用的来源。
最终回复用户前先调用 `save_generated_copy` 保存 title、body、tags、source_topic 和 evidence,再调用 `sync_copy_to_feishu` 同步飞书;工具成功后再输出完整文案,并把返回的 `resource.resource_id` 记为当前文案 ID。数据库记录是权威版本,飞书是协作镜像。

## 第三步:打磨

用户提修改意见时,先调用 `save_user_feedback`;调用参数必须是 `save_user_feedback(feedback=用户原话, target_resource_id=当前文案 ID, feedback_type="revision_request")`,保存修改意见后再迭代修改当前文案,保持分块可复制格式。

## 效果反馈

用户提供发布后数据(如点赞、收藏、评论、转发、浏览、转化、发布时间或笔记链接)时,最终回复用户前先调用 `save_performance_metric` 保存到 Postgres,并绑定对应目标内容资源 ID;如果是刚生成的文案,使用当前文案 ID;如果没有可确定的目标内容,先询问用户确认,不得猜 ID。
用户询问"过去表现如何""为什么推荐这个方向"或要求基于历史效果判断选题时,先对相关资源调用 `get_resource_performance`,再结合检索依据回答;不得凭感觉编造效果数据。

## 风格沉淀(贯穿)

提炼到可复用的表达套路或风格规范时,先用 `search_resources` 检索已有风格记录,在当前上下文合并且保留历史依据;确认后调用 `save_session_snapshot` 保存数据库版本,再调用 `sync_diagnosis_to_feishu` 同步给团队查看。

## 质量检查(交付文案前)
- [ ] 标题有钩子,不平淡
- [ ] 正文像真人小红书笔记,无 AI 腔、无营销八股
- [ ] 标签 5~10 个且相关
- [ ] 选题与文案均有数据依据,非凭空
- [ ] 文案已写入数据库并完成飞书同步,或已明确报告同步失败
