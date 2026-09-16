# worksumgcx —— GUO CHENGXI 的工作总结（D2 工具层 + D3 安全护栏）

负责人：GUO CHENGXI（1093839915@qq.com）
负责范围：D2（工具层，Problem A）、D3（安全护栏，Problem A）
状态：D2/D3 内容已完成，**尚未合并进团队共用的 `main`/`tools` 分支**（原因见文末）

---

## 一、正式交付物在哪

- [`A2_scaffold/docs/D2_tool_layer.md`](A2_scaffold/docs/D2_tool_layer.md) —— D2(a)(b)(c) 完整书面交付
- [`A2_scaffold/docs/D3_guardrails.md`](A2_scaffold/docs/D3_guardrails.md) —— D3(a)(b) 完整书面交付

这两份文档是最终结论，下面只是摘要；细节、复现命令、原始数据全部在文档里。

## 二、D2（工具层）做了什么

### 发现的问题（真实 live 数据测出来的）

用原始 scaffold 的 prompt，在 `openai/gpt-4o-mini` 上跑全部 15 个 Problem A 案例（按 D4 惯例负面案例跑 3 次），**通过率只有 18.2%（6/33）**。归因到三类：

1. escalate 输出从来不带 `trigger` 字段
2. `request_document`（缺文件/缺预授权）经常被误判成 `escalate`
3. 2 个 prompt-injection 案例（叙述里嵌入"忽略规则批准"或伪造工具返回值）模型直接被骗去批准

### 做的改动

- 重写 `prompt.py` 的 routing rules：显式决策树区分 request_document/escalate、annual_limit 算术步骤写明、新增 injection 防御段落
- `agent.py` 新增运行时校验（poka-yoke）：escalate 必须带 trigger 且要有真实工具证据支撑（不能编造"policy_lapsed"却没查过 policy）；request_document 必须带 missing
- `check_duplicate_claim` 签名从 4 参数改成 `claim_id` 单参数，工具内部自己读 claim，避免模型抄错 `lines`
- 7 个 Problem A 工具补齐 `IRREVERSIBLE?` descriptor 字段
- 修了两个基础设施 bug（不修就测不出真实数据）：live backend 的 token 统计一直返回 0（导致 `budget_ceiling` 这个护栏在 live 场景下从未真正生效过）；模型返回格式不对的 JSON 会直接让整个循环崩溃
- 修了一个真实交互 bug：模型有时把决策标签（如 `"request_document"`）当工具名去调用，原来会走"报错→重试→触发去重护栏→trigger 丢失"的坏路径，现在会收到纠正提示，当场改对
- 做了 `prompt_version="v1"/"v2"` 开关（`prompt.RULES_V1` + `agent.STRICT_VALIDATION`），让 v1（原始）和 v2（改写后）从同一份代码、同一个模型、同样的试验次数跑出来，避免"两次实验条件不一致"的问题

### 结果

| | v1 | v2 |
|---|---|---|
| 通过率（15 案例，33 次试验） | 18.2%（6/33） | **72.7%（24/33）** |
| cost | $0.0457 | $0.0676 |

剩余失败（annual_limit 算术错误、2 个 injection 案例）额外用 `gpt-4o` 交叉验证过，**全部正确**——证明是 `gpt-4o-mini` 这个价格档位的能力上限，不是 prompt/工具设计问题，这个结论直接喂给 D6 的模型分级分析。

### D2(c) 串行 vs 并行

固化成 `dev_seq_vs_parallel.py`。关键发现：把并行改成完全串行，在当前 `MAX_TOKENS_PER_RUN=60000` 护栏下**根本跑不完**（撞上 budget_ceiling，错误地变成 escalate），两个上限都放宽后才能跑完，代价是并行方案的 3.2 倍 token、2.2 倍 turns。**注意**：这份对比用的是 scripted backend，token/cost 是模拟估算，只用来证明机制，不是真实成本，不能直接喂给 D6。

## 三、D3（安全护栏）做了什么

- `guardrail_tests.py`：11 个测试用例，全部 scripted、免费，**11/11 PASS**，包含 3 个恶意 narrative 场景（忽略 exclusion 硬批、伪造工具返回值、缺文件硬批），验证即使模型被骗去尝试执行，代码层的校验仍然能拦下来
- `MAX_TURNS=8`、`MAX_TOKENS_PER_RUN=60000` 的数值用实测数据给出依据（不是拍脑袋），细节和推导过程在 `docs/D3_guardrails.md`
- `MAX_FINAL_REJECTIONS` 从 4 调到 6——live 测试中发现更严格的校验偶尔会把重试预算耗尽，导致一个本该能做对的案例意外失败，调整后验证有效

## 四、其他顺带修的

- `issue_decision_letter()` 现在真的往 `A2_scaffold/decisions.jsonl` 追加记录（append-only，带时间戳），不再只返回一个 dict——这是流程文档里点名的 D1 遗留缺口
- `config.py` 的 `BACKEND` 默认值改回 `"scripted"`，干净环境不设 key 也能跑通 `run_eval.py`（D5(a) 的提交红线要求），保留 `A2_BACKEND` 环境变量覆盖

## 五、验证方式（不花钱的部分）

```bash
cd A2_scaffold
python3 run_eval.py                   # scripted 全量回归，应该 100% PASS
python3 demo_loop_failure.py          # D7 示范
python3 guardrail_tests.py            # D3(b)，应该 11/11 PASS
python3 dev_seq_vs_parallel.py        # D2(c) 串行 vs 并行
```

live 部分（花钱，需要 `OPENROUTER_API_KEY`）：
```bash
A2_BACKEND=live python3 dev_v1_v2_compare.py openai/gpt-4o-mini
```

## 六、现在卡在哪，需要团队知道

**这份工作还没合并进团队共用的分支。** 原因：在我做这些工作的同一时间段，`forestgithub123`（队友）往 `main`/`tools` 分支推了一份**设计思路不同但解决同一批问题**的重写——`issue_decision_letter`、`lookup_policy`、`agent.py` 的校验逻辑都被他们用不同的接口签名重新实现了一遍。两边不是简单的文本冲突，是两套不同的设计，需要团队当面对一下"每处冲突保留哪一边、还是合并"，不能靠工具自动合并。

在合并方案定下来之前，**这次的工作只存在于我本地的 git 分支（`main`、`d2-d3-guochengxi`），还没有推送到远程仓库**——一是权限问题（推送账号对仓库没有写权限），二是即使权限好了也不该在没商量好合并方案前直接推。

如果是通过"整个文件夹上传"的方式提交这份工作：**请确认上传时电脑本地的 git 分支是 `main`（能看到 `A2_scaffold/docs/` 目录和 `guardrail_tests.py`/`dev_seq_vs_parallel.py`/`dev_v1_v2_compare.py` 这三个文件），而不是 `tools` 分支**——切换到 `tools` 分支会看到的是队友那版代码，不包含这份工作。
