---
name: topic-content
description: 根据一个内容方向(如露营装备、亲子出游、护肤),从飞书爆款数据中提炼选题并产出小红书文案。当用户给出一个主题/方向、或要求"出选题""写小红书文案""按某方向创作"时使用。
---

# 按方向产出选题 + 文案

这是一个两步式工作流:先给选题菜单,用户选定后再写完整文案。

## 工具边界与检索顺序

保持 DeepAgents 官方 skill/tool 边界:只使用智能体已暴露的工具,不直接访问 Postgres、
不调用 CLI,也不绕过工具边界读取数据。

1. 先调用 `search_resources` 检索统一 Postgres 数据底座,关键词结果是创作的基础。
2. 需要补充语义召回时可调用 `semantic_search_resources`;语义检索失败或不可用时,
   必须回退并继续使用已有的关键词结果。
   注意返回的 `mode`:`semantic`=有相关依据正常用;`insufficient_relevance`=库内无足够相关内容(结果为空),必须明说“当前数据不足”、建议同步或补充数据,不得把空结果当依据、不得编造、也不要擅自改关键词检索凑依据;`keyword_fallback`=语义降级到全文,可用但属降级结果。
3. 对选中的来源调用 `get_resource` 获取详情;仅当关联上下文能增加创作依据时调用
   `graph_expand`。
4. 创作流程不得调用 `read_xhs_data` 或 `read_feishu_wiki` 作为未沉淀兜底;这些只读工具不是内容生成的证据入口。
   统一检索没有可用来源时,先建议或受控调用 `sync_feishu_resources` 把飞书资源沉淀到 Postgres,然后重新检索。
5. 如果同步后仍没有可用来源,或当前无法同步,明确回复“当前数据不足”,建议同步飞书资源或补充数据,不得编造选题、文案或来源依据。

## 第一步:出选题(用户给方向后)

1. 按上述检索顺序查找并筛选来源,记录实际采用来源的资源 ID、标题、依据摘要、源端更新时间和索引时间。`source_updated_at` 是飞书或外部系统的源端更新时间;`indexed_at` 是 Postgres 本地索引更新时间。任一时间缺失时写“未知”,不得猜测或伪造时间。
2. 需要补充知识原子或历史案例时，用 `task` 委派 `knowledge-atom-retriever` 返回带 resource_id 的证据包；分析结论保留在当前上下文，不通过文件传递。
3. 基于分析,产出 **3~5 个选题方向**,按 system prompt「输出协议」里 `xhs_topics` 代码块的格式输出
   (前端据此渲染可点选卡片)。intro 写一句引导语,topics 每项是"一句话角度（预期爆点）",
   evidence 只列实际采用的来源。
   生成结构化 JSON 后,最终回复用户前先调用 `save_generated_topic` 保存 direction、topics 和实际 evidence，再调用 `sync_topic_to_feishu` 同步飞书；数据库成功而飞书失败时保留数据库记录并明确提示同步失败。
4. **停下,请用户选择一个选题。不要在这一步直接写完整文案。**

## 第二步:写文案(用户选定选题后)

为选定选题写完整小红书文案,按 system prompt「输出协议」里 `xhs_copy` 代码块的格式输出
(前端据此渲染带一键复制的文案卡)。evidence 只列实际采用的来源。
生成完整文案 JSON 后,最终回复用户前先调用 `save_generated_copy` 保存 title、body、tags、source_topic 和 evidence，再调用 `sync_copy_to_feishu` 同步飞书；工具成功后再输出完整文案,并把返回的 `resource.resource_id` 记为当前文案 ID。数据库记录是权威版本，飞书是协作镜像。

## 第三步:打磨

用户提修改意见时,先调用 `save_user_feedback`;调用参数必须是 `save_user_feedback(feedback=用户原话, target_resource_id=当前文案 ID, feedback_type="revision_request")`,保存修改意见后再迭代修改当前文案,保持分块可复制格式。

## 效果反馈

用户提供发布后数据(如点赞、收藏、评论、转发、浏览、转化、发布时间或笔记链接)时,最终回复用户前先调用 `save_performance_metric` 保存到 Postgres,并绑定对应目标内容资源 ID;如果是刚生成的文案,使用当前文案 ID;如果没有可确定的目标内容,先询问用户确认,不得猜 ID。
用户询问“过去表现如何”“为什么推荐这个方向”或要求基于历史效果判断选题时,先对相关资源调用 `get_resource_performance`,再结合检索依据回答;不得凭感觉编造效果数据。

## 风格沉淀(贯穿)

提炼到可复用的表达套路或风格规范时，先用 `search_resources` 检索已有风格记录，在当前上下文合并且保留历史依据；确认后调用 `save_session_snapshot` 保存数据库版本，再调用 `sync_diagnosis_to_feishu` 同步给团队查看。

## 质量检查(交付文案前)
- [ ] 标题有钩子,不平淡
- [ ] 正文像真人小红书笔记,无 AI 腔、无营销八股
- [ ] 标签 5~10 个且相关
- [ ] 选题与文案均有数据依据,非凭空
- [ ] 文案已写入数据库并完成飞书同步，或已明确报告同步失败

---

## 数据契约与质量约束

为了确保小红书多智能体联邦系统稳定和数据链路闭环，在执行选题与内容创作工作流时，必须严格遵守以下原则：

1. **防伪与时效性约束**：
   - 严禁臆测、虚构或编造任何数据，如果当前数据不足以支撑推荐，请直接在回复中明示“当前数据不足”，绝对不得编造。
   - 提取的证据中更新时间字段必须对应 `source_updated_at` 与 `indexed_at`。如果源端该数据未知，则在相应字段填“未知”，绝对不得猜。

2. **工具链限制与反面模式（创作流程不得调用限制）**：
   - 创作流程不得调用 `` `read_xhs_data` `` 或 `` `read_feishu_wiki` ``。
   - 所有关于对标素材的读取和飞书外部文档的知识检索，必须依次使用关键词或通过 `` `search_resources` ``、`` `semantic_search_resources` ``、`` `graph_expand` ``、`` `get_resource` `` 进行统一底源资源召回，或者调用 `` `sync_feishu_resources` `` 进行同步。

3. **选题与文案持久化时机（最终回复用户前）**：
   - 最终回复用户前，选题智能体必须先调用 `` `save_generated_topic` `` 落地数据库，并调用 `` `sync_topic_to_feishu` `` 同步至飞书多维表格的选题仓库中，然后向用户展示选题卡。
   - 最终回复用户前，文案智能体必须调用 `` `save_generated_copy` `` 写入数据库，同时调用 `` `sync_copy_to_feishu` `` 同步至飞书多维表格的笔记草稿表中，获取“当前文案 ID”。
   - 用户提出修改反馈时，在迭代修改前必须调用 `` `save_user_feedback` `` 记录用户的具体修正意见（例如当 `feedback_type="revision_request"` 且需要带上文案的 `target_resource_id` 时）。

4. **效果反馈与复利闭环**：
   - 创作者在笔记发布后，如果回填了文案的数据表现（如点赞数、收藏数等），Agent 在最终回复用户前，必须调用 `` `save_performance_metric` `` 将真实表现回填。
   - 推荐新选题或文案时，Agent 必须通过 `` `get_resource_performance` `` 了解该对标的目标内容的过去表现，并在去噪报告中向用户解释为什么推荐该目标内容，不得猜。
