# Sửa 8 điểm mắt trong ảnh kính râm (face_301643) trên CVAT:
#   v = 0 (outside) -> v = 1 (occluded), đặt lại tọa độ theo gọng kính.
# Chạy: python fix_kinh_ram.py   (hỏi mật khẩu CVAT như lab.py, không lưu lại)
# Sau đó chạy: python lab.py export
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab import Cvat, ok, warn, bad, setup_console  # noqa: E402

URL = os.environ.get("CVAT_URL", "http://localhost:8081")
EYES = {"left_eye_outer", "left_eye_inner", "left_eye_upper", "left_eye_lower",
        "right_eye_outer", "right_eye_inner", "right_eye_upper", "right_eye_lower"}
# Tọa độ đo từ ảnh data/faces/face_301643.jpg (520x611), đặt theo gọng kính:
NEW = {
    "left_eye_outer":  (398.0, 252.0),   # đuôi mắt trái (người) = bên phải ảnh
    "left_eye_inner":  (268.0, 250.0),   # khóe trong, cạnh sống mũi
    "left_eye_upper":  (330.0, 240.0),
    "left_eye_lower":  (330.0, 275.0),
    "right_eye_outer": (110.0, 247.0),   # đuôi mắt phải = bên trái ảnh
    "right_eye_inner": (237.0, 245.0),
    "right_eye_upper": (172.0, 235.0),
    "right_eye_lower": (172.0, 270.0),
}


def label_names(cv, task_id):
    """id -> tên điểm (gộp cả label cha và các element của skeleton)."""
    m = {}
    for lb in cv.all(f"/api/labels?task_id={task_id}"):
        m[lb["id"]] = lb["name"]
        for el in lb.get("elements") or []:
            m[el["id"]] = el["name"]
    return m


def find_frame(cv, task_id, image_name):
    try:
        meta = cv.get(f"/api/tasks/{task_id}/data/meta")
        frames = meta.get("frames") or []
        for f in frames:
            name = f.get("name") or f.get("path")
            if name and os.path.basename(name) == image_name:
                return f["frame"]
        # meta phân trang
        while meta.get("next"):
            pass
    except RuntimeError:
        pass
    return None


def collect_shapes(cv, job_id):
    shapes, page = [], 1
    while True:
        d = cv.get(f"/api/jobs/{job_id}/data?page={page}")
        shapes += d.get("shapes") or []
        nxt = d.get("next")
        if not nxt and len(d.get("shapes") or []) == 0 and page > 1:
            break
        if not nxt:
            # CVAT trả đủ trong 1 trang khi ảnh ít
            if len(d.get("shapes") or []) and d.get("size", 0) > len(shapes):
                page += 1
                continue
            break
        page += 1
    return shapes


def main():
    setup_console()
    rec = json.loads(open(os.path.join("src", "exports", "assignment.json"), encoding="utf-8").read())
    tid = rec["tasks"]["faces"]["task_id"]
    jid = rec["tasks"]["faces"]["job_id"]
    cv = Cvat(URL)
    cv.login()

    names = label_names(cv, tid)
    frame = find_frame(cv, tid, "face_301643.jpg")
    if frame is None:  # dự phòng: thứ tự lexicographic khi upload
        frame = sorted(rec["faces"]).index("face_301643.jpg")
    ok(f"Task {tid}, job {jid}, frame {frame} = face_301643.jpg")

    state = cv.get(f"/api/jobs/{jid}").get("state")
    if state == "completed":
        warn("Job đang 'completed', mở lại thành 'in progress' để sửa được...")
        cv.patch(f"/api/jobs/{jid}", {"state": "in progress"})

    shapes = collect_shapes(cv, jid)
    targets = [s for s in shapes
               if s.get("frame") == frame and s.get("type") == "skeleton"
               and names.get(s.get("label_id")) == "face"]
    if len(targets) != 1:
        bad(f"Tìm được {len(targets)} skeleton 'face' ở frame {frame} (cần đúng 1). Dừng.")
        return 1
    sk = targets[0]
    els = sk.get("elements") or []
    if not els:
        bad("Skeleton không có 'elements' (cấu trúc API khác dự kiến). Xem dump fix_debug.json.")
        json.dump(shapes, open("fix_debug.json", "w"), indent=1)
        return 1
    changed = 0
    for el in els:
        nm = names.get(el.get("label_id"))
        if nm in EYES:
            x, y = NEW[nm]
            el["points"] = [x, y]
            el["occluded"] = True
            el["outside"] = False
            changed += 1
        else:
            el["outside"] = False
    # mảng points phẳng của skeleton phải khớp thứ tự elements
    flat = []
    for el in els:
        flat += [el["points"][0], el["points"][1]]
    sk["points"] = flat
    cv.patch(f"/api/jobs/{jid}/data", {"shapes": [sk]})
    ok(f"Đã sửa {changed}/8 điểm mắt: occluded (v = 1), tọa độ theo gọng kính")

    # kiểm lại
    shapes2 = collect_shapes(cv, jid)
    sk2 = [s for s in shapes2 if s.get("id") == sk["id"]][0]
    els2 = {names.get(e.get("label_id")): e for e in (sk2.get("elements") or [])}
    n_occ = sum(1 for nm in EYES if nm in els2 and els2[nm].get("occluded"))
    if n_occ == 8:
        ok("Kiểm lại: cả 8 điểm mắt đều occluded.")
    else:
        bad(f"Kiểm lại chỉ thấy {n_occ}/8 điểm occluded — gửi file fix_debug.json cho trợ lý.")
        json.dump(shapes2, open("fix_debug.json", "w"), indent=1)
        return 1
    if state == "completed":
        cv.patch(f"/api/jobs/{jid}", {"state": "completed"})
        ok("Trả job về 'completed'.")
    print("\n\033[32mXong.\033[0m Chạy tiếp: python lab.py export")
    return 0


if __name__ == "__main__":
    sys.exit(main())
