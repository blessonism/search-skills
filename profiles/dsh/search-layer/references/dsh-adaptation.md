# DSH 适配：设计与验收

此目录是可独立安装的 DSH 技能。仓库顶层 `search-layer` 面向 OpenClaw；分开安装入口是为了保留已有用户的工具名称、凭据查找方式和调用行为。两者不要装到同一个目标目录。

## 请求路径

1. DSH 全局指令选择 `search-layer`。技能工具加载说明；真正发请求的是 `bash` 运行的 Python CLI。`web_fetch` 用于核对具体页面。
2. 助手判断意图、选择查询词和时间范围。一个最多 8 个工作线程的线程池执行查询 × 供应商组合，按输入顺序收集结果。单源失败只影响对应组合。
3. 去重时忽略常见跟踪参数、默认端口和普通片段，同时保留有意义的参数和 hash 路由。展示原始引用地址，并保留各引擎元数据。中文用相邻双字匹配；没有发布日期的记录取中性新鲜度，摘要中的年份不算发布日期。
4. Grok 使用 Responses 的供应商 annotations、action sources 或结构化 legacy citations；正文链接不能单独成为搜索结果。不同引擎找到同一篇文章不是多份独立证据。
5. 只有显式 `--research` 且 Exa 初检命中，才允许符合研究条件的查询发起额外请求。GitHub issue/PR 引用追踪也是显式操作。

## 配置与维护

`runtime_config.py` 从显式 `SEARCH_LAYER_CREDENTIALS` 或 DSH 用户目录加载单个私有文件，再应用各字段的环境变量覆盖。`--doctor` 只检查配置，不验证网络、额度或模型可路由性。在线错误保留脱敏原因和退出状态，Grok 能力缓存可丢弃。

更新时先对照公开源码和本 profile 的差异，保留两种客户端的入口和测试。`scripts/sync_skill_copy.py` 默认只比较；只有传 `--apply` 才会写入审核清单内的文件。配置、缓存和目标独有内容均在清单外。

## 验收

```bash
skill_dir="${DSH_HOME:-$HOME/.dsh}/skills/search-layer"
python3 -B -m unittest discover -s "$skill_dir/scripts/tests"
python3 "$skill_dir/scripts/search.py" --doctor
```

配置好供应商之后，在新 DSH 会话发起一个未点名技能的普通公开查询；核实实际调用、每源状态、去重结果和至少一个可打开的原始页面。只看到技能目录、HTTP 200 或非空模型正文，都不能单独证明检索成功。
