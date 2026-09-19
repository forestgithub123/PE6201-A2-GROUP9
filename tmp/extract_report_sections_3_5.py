#!/usr/bin/env python3
"""Extract completed report Sections 3 and 5 into a standalone DOCX."""
import copy
import os
import zipfile
from xml.etree import ElementTree as ET


SOURCE = "/Users/forstmac/Desktop/NTU/PE6201/A2/output/PE6201_A2_Team_Report_Sections_3_5_Filled.docx"
OUTPUT = "/Users/forstmac/Desktop/NTU/PE6201/A2/output/PE6201_A2_Report_Sections_3_and_5.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS
ET.register_namespace("w", W_NS)


def text_of(element):
    return "".join(node.text or "" for node in element.iter(W + "t")).strip()


def section_slice(children, start_text, end_text):
    start = next(
        index for index, child in enumerate(children)
        if child.tag == W + "p" and text_of(child).startswith(start_text)
    )
    end = next(
        index for index, child in enumerate(children[start + 1:], start + 1)
        if child.tag == W + "p" and text_of(child).startswith(end_text)
    )
    return children[start:end]


def page_break_paragraph():
    paragraph = ET.Element(W + "p")
    run = ET.SubElement(paragraph, W + "r")
    break_element = ET.SubElement(run, W + "br")
    break_element.set(W + "type", "page")
    return paragraph


def main():
    if not os.path.exists(SOURCE):
        raise SystemExit("completed source document not found: %s" % SOURCE)

    with zipfile.ZipFile(SOURCE, "r") as source_zip:
        members = {name: source_zip.read(name) for name in source_zip.namelist()}

    root = ET.fromstring(members["word/document.xml"])
    body = root.find(W + "body")
    children = list(body)
    section_properties = next(
        (copy.deepcopy(child) for child in children if child.tag == W + "sectPr"),
        None,
    )

    section_three = section_slice(
        children, "3  What the evidence showed", "4  What it costs"
    )
    section_five = section_slice(
        children, "5  The two failures", "6  What we would not deploy"
    )

    for child in list(body):
        body.remove(child)
    for child in section_three:
        body.append(copy.deepcopy(child))
    body.append(page_break_paragraph())
    for child in section_five:
        body.append(copy.deepcopy(child))
    if section_properties is not None:
        body.append(section_properties)

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
