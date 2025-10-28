import fitz  # PyMuPDF
import os
import re
import json
import string

# ====== REGEX ======
ANSWER_RE = re.compile(r"^\s*(\d+)\s*[\.\)]")  # "1. ..." / "1) ..."
QUESTION_RE = re.compile(r"^\s*C[âa]u\s*(\d+)\s*[\.:]", re.IGNORECASE)

# ====== FLAGS / BIT ======
UNDERLINE_BIT = 1 << 1  # char_flags bit 1 = underline (giá trị 2)


# ====== HỖ TRỢ HÌNH ======
def extract_hlines(page, height_thresh=2.0, y_tol=2.0):
    """Lấy các đoạn kẻ ngang (x0, x1, y) từ vector graphics."""
    hlines = []
    for path in page.get_drawings():
        for item in path.get("items", []):
            t = item[0]
            if t == "l":  # line
                p0, p1 = item[1], item[2]
                if abs(p0.y - p1.y) <= y_tol:
                    x0, x1 = sorted([p0.x, p1.x])
                    hlines.append((x0, x1, (p0.y + p1.y) / 2.0))
            elif t == "re":  # thin rectangle ~ underline
                r = item[1]
                try:
                    h = r.y1 - r.y0
                    if h <= height_thresh:
                        hlines.append((r.x0, r.x1, r.y1))  # mép dưới như đường kẻ
                except Exception:
                    pass
    return hlines


def spans_have_underline(spans):
    """Ưu tiên đọc underline từ char_flags của span (PyMuPDF >= 1.25.2)."""
    for sp in spans:
        cf = sp.get("char_flags", 0)
        if cf & UNDERLINE_BIT:
            return True
    return False


def rect_overlap_ratio(ax0, ax1, bx0, bx1):
    inter = max(0, min(ax1, bx1) - max(ax0, bx0))
    base = max(ax1 - ax0, 1e-6)
    return inter / base


def answer_has_vector_underline(line_rects, hlines, y_tol=2.0, x_cover=0.5):
    """Fallback: so khớp đường kẻ ngang với từng dòng của đáp án."""
    for x0, y0, x1, y1 in line_rects:
        for lx0, lx1, ly in hlines:
            if abs(ly - y1) <= y_tol:
                if rect_overlap_ratio(x0, x1, lx0, lx1) >= x_cover:
                    return True
    return False


# ====== TIỆN ÍCH KHÁC ======
LETTERS = list(string.ascii_uppercase)  # A, B, C, ...


def num_to_letter(num_str, fallback_index=None):
    """'1' -> 'A', '2' -> 'B'. Nếu không có số, dùng fallback_index (0-based)."""
    if num_str and num_str.isdigit():
        idx = max(0, int(num_str) - 1)
        return LETTERS[idx] if idx < len(LETTERS) else num_str
    if fallback_index is not None and 0 <= fallback_index < len(LETTERS):
        return LETTERS[fallback_index]
    return num_str or ""


def clean_answer_text(full_text):
    """Bỏ tiền tố '1.' / '1)' ở đầu, giữ lại nội dung."""
    t = re.sub(r"^\s*\d+\s*[\.\)]\s*", "", full_text).strip()
    t = re.sub(r"\s+", " ", t)
    return t


# ====== TRÍCH TOÀN BỘ PDF & LƯU JSON ======
def extract_questions_answers_images(pdf_path, out_img_dir, out_json_path):
    os.makedirs(out_img_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    all_results = []  # đưa ra JSON
    current_question = None  # dict cho câu hiện tại
    current_answer = None  # dict cho đáp án đang gom dòng

    def flush_answer():
        """Kết thúc 1 đáp án, tính gạch chân & gom text."""
        nonlocal current_answer, current_question
        if current_answer is None or current_question is None:
            return

        # A) underline từ char_flags
        has_ul = any(
            spans_have_underline(sp_group) for sp_group in current_answer["line_spans"]
        )

        # B) fallback vector underline (theo từng dòng, theo hlines cùng trang)
        if not has_ul:
            for rects, hls in zip(
                current_answer["line_bboxes"], current_answer["line_hlines"]
            ):
                if answer_has_vector_underline([rects], hls):
                    has_ul = True
                    break

        joined_text = " ".join(current_answer["lines"]).strip()
        joined_text = re.sub(r"\s+", " ", joined_text)
        # Bỏ "1." / "1)" đầu dòng
        clean_text = clean_answer_text(joined_text)

        # Gán letter
        letter = current_answer["letter"]  # đã tính khi bắt gặp dòng đầu
        current_question["choices"].append(
            {"letter": letter, "text": clean_text, "is_correct": has_ul}
        )

        current_answer = None

    def flush_question(final=False):
        """Kết thúc 1 câu hỏi -> đẩy sang all_results (và đổi sang cấu trúc JSON mong muốn)."""
        nonlocal current_question, all_results
        if current_question is None:
            return

        # Kết thúc đáp án còn dở
        flush_answer()

        # Xây JSON item
        q_text = " ".join(current_question["question_full"]).strip()
        q_text = re.sub(r"\s+", " ", q_text)

        # danh sách lựa chọn hiển thị "A. text"
        every_choices_list = [
            f"{c['letter']}. {c['text']}" for c in current_question["choices"]
        ]

        # đáp án đúng → letter
        correct_letter = ""
        for c in current_question["choices"]:
            if c["is_correct"]:
                correct_letter = c["letter"]
                break

        # ảnh (nếu đã trích)
        image_path = current_question.get("image_path", "")

        all_results.append(
            {
                "question": q_text,
                "answer": correct_letter,
                "every_choices": every_choices_list,  # nếu muốn chuỗi, có thể: " | ".join(every_choices_list)
                "image_path": image_path,
            }
        )

        current_question = None

    # === DUYỆT TỪNG TRANG, GOM TEXT LINE + IMAGE BLOCK THEO THỨ TỰ Y ===
    for page_num in range(total_pages):
        page = doc[page_num]
        text_dict = page.get_text("dict")
        hlines = extract_hlines(page)

        # Gom element (text lines + images), sort theo y0 rồi x0 để giữ thứ tự đọc
        elements = []
        for block in text_dict.get("blocks", []):
            btype = block.get("type")
            bb = tuple(block.get("bbox", (0, 0, 0, 0)))
            if btype == 0:  # text
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    line_text = " ".join(
                        s.get("text", "").strip() for s in spans if s.get("text")
                    )
                    line_text = re.sub(r"\s+", " ", line_text).strip()
                    if not line_text:
                        continue
                    elements.append(
                        {
                            "type": "text",
                            "text": line_text,
                            "spans": spans,
                            "bbox": tuple(line.get("bbox", (0, 0, 0, 0))),
                            "hlines": hlines,  # vector lines của trang này (dùng fallback)
                        }
                    )
            elif btype == 1:  # image
                xref = block.get("xref")
                if xref:
                    elements.append({"type": "image", "xref": int(xref), "bbox": bb})

        # sort
        elements.sort(key=lambda e: (e["bbox"][1], e["bbox"][0]))

        # === ĐỌC ELEMENT THEO THỨ TỰ ===
        for el in elements:
            if el["type"] == "text":
                text = el["text"]

                # Bắt đầu câu hỏi mới
                m_q = QUESTION_RE.match(text)
                if m_q:
                    # chốt câu trước
                    flush_question()

                    q_num = int(m_q.group(1))
                    current_question = {
                        "number": q_num,
                        "question_full": [text],  # có thể kéo dài nhiều dòng
                        "choices": [],
                        "image_path": "",  # sẽ gán khi gặp ảnh đầu tiên trong phạm vi câu này
                    }
                    current_answer = None
                    continue

                # Nếu đang trong 1 câu hỏi, thử xem đây có phải dòng đáp án mới
                if current_question is not None:
                    m_a = ANSWER_RE.match(text)
                    if m_a:
                        # chốt đáp án trước (nếu có)
                        flush_answer()
                        num_str = m_a.group(1) if m_a else None
                        # map sang letter
                        # ưu tiên từ số ở tiền tố; nếu bị lỗi, fallback theo thứ tự xuất hiện
                        fallback_idx = len(current_question["choices"])
                        letter = num_to_letter(num_str, fallback_index=fallback_idx)

                        current_answer = {
                            "lines": [text],
                            "line_spans": [el["spans"]],
                            "line_bboxes": [el["bbox"]],
                            "line_hlines": [el["hlines"]],
                            "letter": letter,
                        }
                        continue

                    # Nếu đang gom 1 đáp án => đây là dòng tiếp nối của đáp án
                    if current_answer is not None:
                        current_answer["lines"].append(text)
                        current_answer["line_spans"].append(el["spans"])
                        current_answer["line_bboxes"].append(el["bbox"])
                        current_answer["line_hlines"].append(el["hlines"])
                    # Nếu chưa đến đáp án, thì đây là phần mô tả dài của câu hỏi
                    elif current_question is not None:
                        current_question["question_full"].append(text)

            elif el["type"] == "image":
                # Ảnh đầu tiên kể từ khi thấy "Câu N" cho tới trước "Câu N+1"
                if current_question is not None and not current_question.get(
                    "image_path"
                ):
                    try:
                        img = doc.extract_image(el["xref"])
                        img_bytes = img["image"]
                        ext = img.get("ext", "png") or "png"
                        filename = f"Q{current_question['number']}.{ext.lower()}"
                        save_path = os.path.join(out_img_dir, filename)
                        # nếu đã tồn tại (câu bị lặp ảnh), ghi đè nhẹ
                        with open(save_path, "wb") as f:
                            f.write(img_bytes)
                        current_question["image_path"] = save_path
                    except Exception:
                        # Không cản luồng nếu trích ảnh lỗi
                        pass

    # Hết tài liệu: chốt phần đang dở
    flush_question(final=True)

    doc.close()

    # Ghi JSON
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    return all_results


if __name__ == "__main__":
    # === THAY ĐƯỜNG DẪN Ở ĐÂY ===
    pdf_path = r"C:\Users\ha.phan\Downloads\273963059_Bộ 600 câu hỏi dùng cho sát hạch lái xe cơ giới đường bộ.pdf"
    out_img_dir = r"C:\Users\ha.phan\Downloads\bo600_images"
    out_json_path = r"C:\Users\ha.phan\Downloads\bo600_questions.json"

    try:
        results = extract_questions_answers_images(pdf_path, out_img_dir, out_json_path)
        print(f"✅ Đã trích {len(results)} câu hỏi.")
        print(f"💾 JSON: {out_json_path}")
        print(f"🖼️ Ảnh lưu tại: {out_img_dir}")
    except FileNotFoundError:
        print(f"❌ Không tìm thấy file: {pdf_path}")
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
