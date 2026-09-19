#!/usr/bin/env python3
"""Add audited V1/V2 evidence and the latest model runs to two Word files."""

import copy
import os
import tempfile
import zipfile
from xml.etree import ElementTree as ET


ROOT = "/Users/forstmac/Desktop/NTU/PE6201/A2"
MODEL_DOC = os.path.join(
    ROOT, "output", "Problem A Live Model Battery Results and Analysis.docx"
)
REPORT_DOC = os.path.join(
    ROOT, "output", "PE6201_A2_Report_Sections_3_and_5.docx"
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W = "{%s}" % W_NS
ET.register_namespace("w", W_NS)


def element_text(element):
    return "".join(node.text or "" for node in element.iter(W + "t"))


def set_paragraph_text(paragraph, text):
    ppr = paragraph.find(W + "pPr")
    first_run = paragraph.find(W + "r")
    rpr = None
    if first_run is not None and first_run.find(W + "rPr") is not None:
        rpr = copy.deepcopy(first_run.find(W + "rPr"))

    for child in list(paragraph):
        if child is not ppr:
            paragraph.remove(child)

    run = ET.SubElement(paragraph, W + "r")
    if rpr is not None:
        run.append(rpr)
    node = ET.SubElement(run, W + "t")
    if text[:1].isspace() or text[-1:].isspace():
        node.set("{%s}space" % XML_NS, "preserve")
    node.text = text


def set_cell_text(cell, text):
    paragraphs = cell.findall(W + "p")
    if paragraphs:
        set_paragraph_text(paragraphs[0], text)
        for extra in paragraphs[1:]:
            cell.remove(extra)
    else:
        paragraph = ET.SubElement(cell, W + "p")
        set_paragraph_text(paragraph, text)


def set_row(row, values):
    cells = row.findall(W + "tc")
    if len(cells) != len(values):
        raise ValueError("row has %d cells; expected %d" % (len(cells), len(values)))
    for cell, value in zip(cells, values):
        set_cell_text(cell, value)


def find_paragraph(body, text, startswith=False):
    for child in body:
        if child.tag != W + "p":
            continue
        candidate = element_text(child).strip()
        if (startswith and candidate.startswith(text)) or (not startswith and candidate == text):
            return child
    raise KeyError("paragraph not found: %s" % text[:100])


def find_table(body, first_header, column_count=None):
    for child in body:
        if child.tag != W + "tbl":
            continue
        rows = child.findall(W + "tr")
        if not rows:
            continue
        cells = rows[0].findall(W + "tc")
        if not cells:
            continue
        if element_text(cells[0]).strip() != first_header:
            continue
        if column_count is not None and len(cells) != column_count:
            continue
        return child
    raise KeyError("table not found: %s" % first_header)


def insert_after(body, anchor, elements):
    position = list(body).index(anchor) + 1
    for element in elements:
        body.insert(position, element)
        position += 1


def paragraph_like(template, text):
    paragraph = copy.deepcopy(template)
    set_paragraph_text(paragraph, text)
    return paragraph


def make_table_from_template(template, values):
    table = copy.deepcopy(template)
    rows = table.findall(W + "tr")
    row_template = copy.deepcopy(rows[-1])
    for row in rows:
        table.remove(row)
    for index, row_values in enumerate(values):
        row = copy.deepcopy(rows[0] if index == 0 else row_template)
        set_row(row, row_values)
        table.append(row)
    return table


def append_rows(table, rows_to_add):
    rows = table.findall(W + "tr")
    template = rows[-1]
    existing_first_cells = {
        element_text(row.findall(W + "tc")[0]).strip()
        for row in rows
        if row.findall(W + "tc")
    }
    for values in rows_to_add:
        if values[0] in existing_first_cells:
            continue
        row = copy.deepcopy(template)
        set_row(row, values)
        table.append(row)


def write_docx(path, updater):
    with zipfile.ZipFile(path, "r") as source:
        members = {name: source.read(name) for name in source.namelist()}
    root = ET.fromstring(members["word/document.xml"])
    body = root.find(W + "body")
    updater(body)
    members["word/document.xml"] = ET.tostring(
        root, encoding="utf-8", xml_declaration=True
    )
    fd, temporary_path = tempfile.mkstemp(
        prefix="docx-update-", suffix=".docx", dir=os.path.dirname(path)
    )
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED) as target:
            for name, data in members.items():
                target.writestr(name, data)
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def update_model_doc(body):
    if any(
        child.tag == W + "p"
        and element_text(child).strip() == "2.1 GPT-4o mini V1 and V2 Evidence Audit"
        for child in body
    ):
        return

    section_three = find_paragraph(body, "3 各模型具体结果与原因分析")
    heading_template = find_paragraph(body, "4.1 最终通过率与原始模型质量不是同一个指标")
    body_template = find_paragraph(body, "重要限制。", startswith=True)
    comparison_table = find_table(body, "Model", 7)

    audit_heading = paragraph_like(
        heading_template, "2.1 GPT-4o mini V1 and V2 Evidence Audit"
    )
    audit_table = make_table_from_template(
        comparison_table,
        [
            ["Evidence version", "Overall", "Approve", "Negative", "Median worst turns", "Tokens", "Cost or status"],
            ["Supplied V1 stored result", "91/109 (83.5%)", "37/40", "54/69 stored", "2/4", "1,081,822 in; 57,252 out", "US$0.1311"],
            ["V1 current-harness regrade", "106/109 (97.2%)", "37/40", "69/69", "2/4", "same trace", "15 grading mismatches corrected"],
            ["Verified V2 result", "109/109 (100.0%)", "40/40", "69/69", "4/5", "1,369,108 in; 43,694 out", "US$0.1544"],
        ],
    )
    audit_body = paragraph_like(
        body_template,
        "The supplied V1 file reports 91/109, but 15 failed rows contain correct negative decisions and are labelled only 'negative case marked as failed'. Re-running the current deterministic code check on the same records gives 106/109, including 69/69 negative trials. More importantly, after configuration, grading and timing fields are removed, the V1 trace matches the archived Gemini 2.5 trace. It therefore cannot support a causal claim that removing a GPT-4o mini feature reduced performance. The defensible comparison is limited to the supplied stored score, the current-harness regrade, and the independently verified GPT-4o mini V2 run. A clean GPT-4o mini V1 rerun is required before the difference is reported as an ablation result.",
    )
    position = list(body).index(section_three)
    for element in (audit_heading, audit_table, audit_body):
        body.insert(position, element)
        position += 1

    evidence_table = find_table(body, "Model", 3)
    append_rows(
        evidence_table,
        [["GPT-4o mini V1 candidate", "results_V1_live_gpt-4o-mini.json", "gpt-4o-mini in config; trace provenance not independently verified"]],
    )


def update_report_doc(body):
    model_table = find_table(body, "Model", 6)
    append_rows(
        model_table,
        [
            ["DeepSeek Flash Latest", "103/109 (94.5%)", "66/69 (95.7%)", "2", "US$0.1632*", "Six empty-content responses caused backend-unavailable stops."],
            ["Claude Sonnet 5 negative set", "69/69 negative only", "69/69 (100.0%)", "2", "US$0.1541*", "Negative stress test only; 40 approve cases were not tested."],
        ],
    )

    negative_table = find_table(body, "Case", 5)
    negative_rows = negative_table.findall(W + "tr")
    replacements = {
        "CLM-9301": "Gemini 2.5 falsely escalated; the other five full-battery models approved.",
        "CLM-8952": "19/21 trials passed across six full model runs and the Claude negative stress test; Qwen produced two backend-unavailable records.",
        "CLM-9203": "18/21 trials passed; Gemini 3.8 failed twice and GPT-5.6 Luna failed once after repeated unsupported finals.",
    }
    for row in negative_rows[1:]:
        cells = row.findall(W + "tc")
        case_id = element_text(cells[0]).strip()
        if case_id in replacements:
            set_cell_text(cells[3], replacements[case_id])

    if not any(
        child.tag == W + "p"
        and element_text(child).strip() == "3.5 GPT-4o mini V1 and V2 Evidence Audit"
        for child in body
    ):
        section_five = find_paragraph(body, "5  The two failures")
        heading_template = find_paragraph(body, "3.4  What Negative and Guardrail Cases Caught")
        body_template = find_paragraph(body, "The model battery shows", startswith=True)
        audit_heading = paragraph_like(
            heading_template, "3.5 GPT-4o mini V1 and V2 Evidence Audit"
        )
        audit_paragraph = paragraph_like(
            body_template,
            "The supplied GPT-4o mini V1 file reports 91/109 (83.5%), while current-harness regrading gives 106/109 because 15 correct negative cases were mislabelled. The independently verified GPT-4o mini V2 run passed 109/109 (100.0%). However, the V1 trace matches the archived Gemini 2.5 trace after non-behavioural fields are removed. The difference must therefore be treated as an evidence-quality finding, not as proof that a removed feature caused the performance drop. A clean GPT-4o mini V1 rerun is required before this is presented as an ablation result.",
        )
        position = list(body).index(section_five)
        body.insert(position, audit_heading)
        body.insert(position + 1, audit_paragraph)

    last_paragraph = find_paragraph(body, "The full scripted battery confirmed", startswith=True)
    boundary_text = (
        "Evidence boundary for the V1/V2 comparison: the supplied V1 trace is not used as a third D7 failure. "
        "Its records match the archived Gemini 2.5 trace after non-behavioural fields are removed, and 15 correct "
        "negative decisions were misgraded. It is an audit finding rather than a valid working-agent-minus-X "
        "reproduction. The report should use it to justify a clean rerun, not to claim a causal V1/V2 ablation result."
    )
    if not any(
        child.tag == W + "p" and element_text(child).strip().startswith("Evidence boundary for the V1/V2")
        for child in body
    ):
        insert_after(body, last_paragraph, [paragraph_like(last_paragraph, boundary_text)])


def main():
    write_docx(MODEL_DOC, update_model_doc)
    write_docx(REPORT_DOC, update_report_doc)
    print(MODEL_DOC)
    print(REPORT_DOC)


if __name__ == "__main__":
    main()
