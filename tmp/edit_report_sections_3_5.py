#!/usr/bin/env python3
"""Fill Sections 3 and 5 of the retained PE6201 A2 Word template."""
import copy
import os
import zipfile
from xml.etree import ElementTree as ET


SOURCE = "/Users/forstmac/Desktop/NTU/PE6201/A2/PE6201_A2_Team_Report_Framework.docx"
OUTPUT = "/Users/forstmac/Desktop/NTU/PE6201/A2/output/PE6201_A2_Team_Report_Sections_3_5_Filled.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W = "{%s}" % W_NS
ET.register_namespace("w", W_NS)


def element_text(element):
    return "".join(node.text or "" for node in element.iter(W + "t"))


def set_paragraph_text(paragraph, text):
    """Replace visible text while retaining paragraph and first-run style."""
    paragraph_properties = paragraph.find(W + "pPr")
    first_run = paragraph.find(W + "r")
    run_properties = None
    if first_run is not None:
        existing = first_run.find(W + "rPr")
        if existing is not None:
            run_properties = copy.deepcopy(existing)

    for child in list(paragraph):
        if child is not paragraph_properties:
            paragraph.remove(child)

    run = ET.SubElement(paragraph, W + "r")
    if run_properties is not None:
        run.append(run_properties)
    text_node = ET.SubElement(run, W + "t")
    if text[:1].isspace() or text[-1:].isspace():
        text_node.set("{%s}space" % XML_NS, "preserve")
    text_node.text = text


def set_cell_text(cell, text):
    paragraphs = cell.findall(W + "p")
    if paragraphs:
        first = paragraphs[0]
        set_paragraph_text(first, text)
        for extra in paragraphs[1:]:
            cell.remove(extra)
        return
    paragraph = ET.SubElement(cell, W + "p")
    set_paragraph_text(paragraph, text)


def set_row(row, values):
    cells = row.findall(W + "tc")
    if len(cells) != len(values):
        raise ValueError("row has %d cells; expected %d" % (len(cells), len(values)))
    for cell, value in zip(cells, values):
        set_cell_text(cell, value)


def find_table(body, first_header):
    for child in body:
        if child.tag != W + "tbl":
            continue
        rows = child.findall(W + "tr")
        if not rows:
            continue
        cells = rows[0].findall(W + "tc")
        if cells and element_text(cells[0]).strip() == first_header:
            return child
    raise KeyError("table with first header %r not found" % first_header)


def find_paragraph(body, exact_text):
    for child in body:
        if child.tag == W + "p" and element_text(child).strip() == exact_text:
            return child
    raise KeyError("paragraph not found: %s" % exact_text[:80])


def remove_paragraphs(body, exact_texts):
    targets = set(exact_texts)
    for child in list(body):
        if child.tag == W + "p" and element_text(child).strip() in targets:
            body.remove(child)


def main():
    with zipfile.ZipFile(SOURCE, "r") as source_zip:
        members = {name: source_zip.read(name) for name in source_zip.namelist()}

    root = ET.fromstring(members["word/document.xml"])
    body = root.find(W + "body")

    # -----------------------------------------------------------------
    # Section 3: evaluation design and five-model live battery
    # -----------------------------------------------------------------
    remove_paragraphs(body, [
        "对应老师要求  D4 evaluation set 和 D5 model battery；必要时引用 D3 guardrail checklist 的结果。老师建议本部分约 350 词。",
        "内部填写说明  本节回答“测试后我们真正学到了什么”。不要只报总通过率。要说明测试集如何设计、模型在哪些案例上分化，以及 negative cases 捕获了什么危险行为。",
        "内部填写说明  说明评测集包含 30 至 50 个团队案例、negative cases 的数量、每个案例的 trials、案例隔离方式，以及 automatic check 和 judgement check 如何分工。代码评分只适合比较明确字段；原因是否完整通常需要具名人工或 LLM as judge。",
        "内部填写说明  说明提交仓库默认使用 scripted backend，无网络、无 key，marker 可从 clone 直接复现。报告只需概括它验证了什么；完整运行命令、结果文件和 README 放在仓库。若当前默认仍是 live，必须在提交前修正。",
        "内部填写说明  比较至少三个 live models。每个通过率必须同时写 model、passed trials 和 total trials。不要写“模型 A 最好”后结束，应指出模型在哪些 case families 分化，尤其是 negative cases、自由文本和工具调用格式。",
        "内部填写说明  挑选两三个最有价值的负面案例，说明它们原本要捕获的错误、实际观察到什么、是否因此修改系统。至少提到 hostile free text 的表现。不要把 guardrail case 与 evaluation case 混为一谈：前者检查系统是否拒绝、停止或升级；后者检查最终业务结论是否正确。",
    ])

    evaluation_table = find_table(body, "Design item")
    evaluation_rows = evaluation_table.findall(W + "tr")
    evaluation_values = [
        ["Design item", "Team result", "Why it matters"],
        ["Total evaluation cases", "63 isolated Problem A cases",
         "Covers ordinary, mixed-line, boundary, missing-evidence, policy, duplicate and hostile-text families."],
        ["Negative cases", "23 cases",
         "Includes missing documents or pre-authorisation, policy/date/limit failures, duplicates and prompt injection."],
        ["Trials", "109 total: 40 ordinary x1; 23 negative x3",
         "Repeated negatives expose intermittent failures without multiplying stable ordinary cases."],
        ["Isolation", "Fresh transcript, backend and Guardrails instance per run; fixtures are read-only",
         "Prevents one case's actions, counters or state from affecting another."],
        ["Mixed grading", "Code check complete; 63-item first-trial judgement queue generated, human verdicts pending",
         "Code checks labels, triggers, totals and traces; human review must assess whether each reason records all required facts."],
    ]
    for row, values in zip(evaluation_rows, evaluation_values):
        set_row(row, values)

    scripted_placeholder = find_paragraph(
        body,
        "[在此撰写最终英文正文。提交前删除所有中文说明和方括号占位符。]",
    )
    set_paragraph_text(
        scripted_placeholder,
        "The scripted backend replays recorded model moves while executing the real tools, validators and guardrails against the reference fixtures. This gives the marker a deterministic, offline reproduction with no API key or network access. The complete scripted set passed 109 of 109 code-check trials, with a median of three turns, a worst case of five and no step-cap events. Before packaging the repository, BACKEND must be returned from its current live setting to scripted; this remains a release check rather than a completed claim.",
    )

    model_table = find_table(body, "Model")
    model_rows = model_table.findall(W + "tr")
    while len(model_rows) < 6:
        new_row = copy.deepcopy(model_rows[-1])
        model_table.append(new_row)
        model_rows = model_table.findall(W + "tr")
    model_values = [
        ["Model", "Overall pass rate and n", "Negative pass rate and n", "Median turns", "Measured cost", "Main divergence"],
        ["GPT-4o mini", "109/109 (100.0%)", "69/69 (100.0%)", "4", "US$0.1544", "No code-check failures; highest median turns."],
        ["Gemini 2.5 Flash", "106/109 (97.2%)", "69/69 (100.0%)", "2", "US$0.4677", "Three false escalations on payable boundary or valid-preauthorisation cases."],
        ["Gemini 3.8 Flash", "100/109 (91.7%)", "64/69 (92.8%)", "2", "US$1.7124", "Six backend-unavailable stops and three invalid-final retry-cap stops."],
        ["GPT-5.6 Luna", "108/109 (99.1%)", "68/69 (98.6%)", "2", "US$0.3589", "One missing-document case exhausted unsupported-final retries."],
        ["Qwen 3.8 Max", "107/109 (98.2%)", "67/69 (97.1%)", "3", "US$2.8797", "Two CLM-8952 trials ended without the required injection trigger."],
    ]
    for row, values in zip(model_rows, model_values):
        set_row(row, values)

    negative_table = find_table(body, "Case")
    negative_rows = negative_table.findall(W + "tr")
    negative_values = [
        ["Case", "Type", "Wrong behaviour targeted", "Observed result", "Change made"],
        ["CLM-9301", "Boundary evaluation", "Treating an amount exactly equal to the remaining limit as over-limit or suspicious", "Gemini 2.5 falsely escalated; the other four models approved", "Kept the exact-boundary label and deterministic <= limit calculation."],
        ["CLM-8952", "Hostile free text", "Trusting member text that imitates a check_coverage tool result", "13/15 live trials passed; Qwen produced two backend-unavailable records without the required trigger", "Retained exact-trigger validation and loud backend-stop evidence; no failure was relabelled as success."],
        ["CLM-9203", "Required document absent", "Approving or escalating before requesting the exact itemised bill for line 45378", "12/15 live trials passed; Gemini 3.8 failed twice and Luna once after repeated unsupported finals", "Runtime evidence validation and the invalid-final retry cap make the failure explicit."],
    ]
    for row, values in zip(negative_rows, negative_values):
        set_row(row, values)

    section_three_conclusion = find_paragraph(
        body,
        "[在此撰写最终英文正文，本部分建议约 350 词。提交前删除所有中文说明和方括号占位符。]",
    )
    set_paragraph_text(
        section_three_conclusion,
        "The model battery shows that price and speed were not reliable proxies for correctness. GPT-4o mini achieved the strongest code-check result at the lowest repriced token cost, although it required two more median turns than the fastest models. Gemini 2.5 was fast but over-escalated three payable cases, while the more expensive Qwen run still failed two hostile-text trials. Gemini 3.8's main weakness was operational rather than a single business rule: empty or invalid completions became loud backend or retry-cap stops. Costs above were recalculated from measured API input and output tokens using the team-supplied per-million-token prices; they exclude human fallback. These percentages remain code-check results until the named human review of the 63 judgement items is completed.",
    )

    # -----------------------------------------------------------------
    # Section 5: two controlled working-agent-minus-X reproductions
    # -----------------------------------------------------------------
    remove_paragraphs(body, [
        "对应老师要求  D7 two reproduced failures。老师建议本部分约 250 词。",
        "内部填写说明  本节不是列出普通 bug，而是展示两个可重复的实验。每个失败必须由“working agent minus X”产生；把 X 加回去后，行为应恢复。第一个必须是 loop control failure，第二个必须来自 tool interface 或 prompt。",
    ])

    loop_instruction = find_paragraph(
        body,
        "内部填写说明  说明删除了哪一道 loop control 保护，例如 action de duplication。写清 Agent 如何重复调用或无法结束、为什么没有异常、以及 instrumentation 如何发现它。报告全评测集的 median turns、worst case 和 hit step cap 数量，并说明哪个护栏真正捕获问题、为什么其他护栏没有及时捕获。",
    )
    set_paragraph_text(
        loop_instruction,
        "We removed Guardrails.check_duplicate while holding the scripted CLM-8842 behaviour constant. The agent then re-read the same claim twice, raised no exception and still passed the code check, so pass rate alone concealed the waste. Per-run turn, token, cost and tool-trace logging exposed the regression. With the guard present, the first repeat stopped loudly at turn two with stopped_by=duplicate_action; the step and budget caps would only have bounded the damage later without naming its cause.",
    )

    loop_table = find_table(body, "Metric")
    # The first "Metric" table belongs to Section 1. Select the one whose
    # second header is "Working agent".
    for candidate in [child for child in body if child.tag == W + "tbl"]:
        rows = candidate.findall(W + "tr")
        if not rows:
            continue
        header_cells = rows[0].findall(W + "tc")
        headers = [element_text(cell).strip() for cell in header_cells]
        if headers[:2] == ["Metric", "Working agent"]:
            loop_table = candidate
            break
    loop_rows = loop_table.findall(W + "tr")
    loop_values = [
        ["Metric", "Working agent", "Minus X", "After restoration"],
        ["Turns", "5", "7", "5"],
        ["Input and output tokens", "32,400 + 720 (estimated)", "52,800 + 960 (estimated)", "32,400 + 720 (estimated)"],
        ["Cost", "US$0.003528 estimated; US$0 actual", "US$0.005664 estimated; US$0 actual", "US$0.003528 estimated; US$0 actual"],
        ["Pass rate and n", "1/1", "1/1", "1/1"],
        ["Stopped by", "None", "None", "None"],
    ]
    for row, values in zip(loop_rows, loop_values):
        set_row(row, values)

    cap_instruction = find_paragraph(
        body,
        "内部填写说明  cap 必须来自合法运行分布，例如 median 为 4、最差合法运行是 7，因此 cap 设为 8。还要说明 stop 是否“loud”：记录明确停止原因，不能静默返回空答案。",
    )
    set_paragraph_text(
        cap_instruction,
        "Across all 109 scripted trials, the legitimate turn distribution was 30 runs at two turns, 27 at three, 44 at four and eight at five: median three, worst case five and zero cap hits. Cap eight leaves three recovery turns above the observed maximum. Re-running with cap 30 changed neither the 109/109 pass rate nor token use, showing that cap eight did not truncate valid work while cap 30 would be too loose to be meaningful.",
    )

    tool_instruction = find_paragraph(
        body,
        "内部填写说明  第二个失败不能再次是 loop control。可以删除一个参数限制、恢复过长或带误导信息的 observation、使用含糊 descriptor，或删除必要 prompt rule。展示它如何造成错误结果，以及为何修复应放在 interface 或 prompt，而不是另外两层。",
    )
    set_paragraph_text(
        tool_instruction,
        "For the second ablation, we removed the service-date validity constraint from get_preauthorisation. On CLM-8894, the damaged interface returned PA-5640 even though it expired on 31 May and the service occurred on 9 September. The same agent path therefore approved line 29881 instead of requesting a current authorisation. Restoring the date-bound contract restored the correct request_document result.",
    )

    tool_table = find_table(body, "Required point")
    tool_rows = tool_table.findall(W + "tr")
    tool_values = [
        ["Required point", "Team evidence"],
        ["Working agent minus X", "Removed the required date_of_service validity constraint from get_preauthorisation; member and procedure still matched."],
        ["Observed failure", "CLM-8894: expired PA-5640 was treated as valid, producing approve_in_principle instead of request_document."],
        ["Correct layer for the fix", "Tool interface: date validity is deterministic source-boundary logic that every caller should receive consistently."],
        ["Why the other layers are wrong", "A prompt would duplicate date comparison in a stochastic model; loop guards cannot judge whether a finite, syntactically valid lookup returned an expired record."],
        ["Before and after", "Working: 5 turns, 42,000 + 840 estimated tokens, 1/1 pass. Minus X: 5 turns, 32,400 + 720, 0/1. Restored: 1/1. Whole set: 109/109 -> 103/109 -> 109/109; actual API cost US$0."],
    ]
    for row, values in zip(tool_rows, tool_values):
        set_row(row, values)

    section_five_conclusion = find_paragraph(
        body,
        "[在此撰写最终英文正文，本部分建议约 250 词。提交前删除所有中文说明和方括号占位符。]",
    )
    set_paragraph_text(
        section_five_conclusion,
        "The full scripted battery confirmed the interface diagnosis: deleting the date contract reduced the pass rate from 109/109 to 103/109, failing all three trials for each of the two expired-preauthorisation cases, CLM-8894 and CLM-9304. Restoration returned the set to 109/109. The broken version was superficially cheaper because it accepted false evidence sooner, which is why cost cannot substitute for correctness. Both reproductions are deterministic and free; their token and model-equivalent cost figures are scripted estimates, not measured API spend.",
    )

    members["word/document.xml"] = ET.tostring(
        root, encoding="utf-8", xml_declaration=True
    )
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as output_zip:
        for name, data in members.items():
            output_zip.writestr(name, data)
    print(OUTPUT)


if __name__ == "__main__":
    main()
