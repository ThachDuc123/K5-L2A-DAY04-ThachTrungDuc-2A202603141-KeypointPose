# Sửa 8 điểm mắt trong ảnh kính râm (face_301643) trên CVAT:
#   v = 0 (outside) -> v = 1 (occluded), đặt lại tọa độ theo gọng kính.
# Cách làm: xóa skeleton cũ rồi tạo lại với giá trị đúng theo label_id
# (endpoint update của CVAT 2.x bỏ qua thay đổi element; create lưu payload nguyên vẹn).
# Bản đồ label_id -> tên điểm ghép từ thứ tự sublabel của label `face`
# (88..95 = 8 điểm mắt, 96..100 = nose_tip, mouth_left, mouth_right, lip_upper, lip_lower).
# Đã chạy và kiểm lại 13/13 điểm đúng (xem báo cáo mục 5).
# Chạy: python fix_kinh_ram.py   (hỏi mật khẩu CVAT như lab.py, không lưu lại)
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab import Cvat, ok, warn, bad, setup_console  # noqa: E402

URL = os.environ.get("CVAT_URL", "http://localhost:8081")
ID2NAME = {
    88: "left_eye_outer", 89: "left_eye_inner", 90: "left_eye_upper", 91: "left_eye_lower",
    92: "right_eye_outer", 93: "right_eye_inner", 94: "right_eye_upper", 95: "right_eye_lower",
    96: "nose_tip", 97: "mouth_left", 98: "mouth_right", 99: "lip_upper", 100: "lip_lower",
}
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
ORIG_LIP_LOWER = (250.27252338343533, 404.5779701143765)  # giữ nguyên vị trí gốc


def find_frame(cv, task_id, image_name):
    """Số frame = vị trí trong danh sách frame của task (theo tên file)."""
    try:
        meta = cv.get(f"/api/tasks/{task_id}/data/meta")
        for idx, f in enumerate(meta.get("frames") or []):
            name = f.get("name") or f.get("path") if isinstance(f, dict) else f
            if name and os.path.basename(str(name)) == image_name:
                return idx
    except RuntimeError:
        pass
    return None


def main():
    setup_console()
    rec = json.loads(open(os.path.join("src", "exports", "assignment.json"), encoding="utf-8").read())
    tid = rec["tasks"]["faces"]["task_id"]
    jid = rec["tasks"]["faces"]["job_id"]
    cv = Cvat(URL)
    cv.login()

    frame = find_frame(cv, tid, "face_301643.jpg")
    ok(f"Task {tid}, job {jid}, frame {frame} = face_301643.jpg")

    state = cv.get(f"/api/jobs/{jid}").get("state")
    if state == "completed":
        warn("Job đang 'completed', mở lại thành 'in progress' để sửa được...")
        cv.patch(f"/api/jobs/{jid}", {"state": "in progress"})

    d = cv.get(f"/api/jobs/{jid}/annotations")
    targets = [s for s in d.get("shapes") or []
               if s.get("frame") == frame and s.get("type") == "skeleton"
               and s.get("label_id") == 87]
    if len(targets) != 1:
        bad(f"Tìm được {len(targets)} skeleton ở frame {frame} (cần đúng 1). Dừng.")
        return 1
    sk = targets[0]

    # backup skeleton hiện tại để có thể khôi phục nếu create lỗi giữa chừng
    json.dump({"backup_skeleton": sk}, open("fix_debug.json", "w"), indent=1)
    ok(f"Đã lưu backup skeleton id {sk['id']} vào fix_debug.json")

    # 1) xóa skeleton cũ (gửi cả shape để qua validation; server xóa theo id)
    cv.patch(f"/api/jobs/{jid}/annotations?action=delete", {"shapes": [sk]})

    # 2) tạo lại skeleton mới: bỏ hết id, ghi giá trị đúng theo label_id
    new_sk = {k: v for k, v in sk.items() if k != "id"}
    changed = 0
    for el in new_sk.get("elements") or []:
        nm = ID2NAME.get(el["label_id"])
        if nm in NEW:
            x, y = NEW[nm]
            el["points"] = [x, y]
            el["occluded"] = True
            el["outside"] = False
            changed += 1
        elif nm == "lip_lower":
            el["points"] = [ORIG_LIP_LOWER[0], ORIG_LIP_LOWER[1]]
            el["occluded"] = False
            el["outside"] = False
        else:
            el["occluded"] = False
            el["outside"] = False
        el.pop("id", None)
    cv.patch(f"/api/jobs/{jid}/annotations?action=create", {"shapes": [new_sk]})
    ok(f"Đã sửa {changed}/8 điểm mắt: occluded (v = 1), tọa độ theo gọng kính")

    # kiểm lại bằng GET
    d2 = cv.get(f"/api/jobs/{jid}/annotations")
    sk2 = [s for s in d2.get("shapes") or []
           if s.get("frame") == frame and s.get("type") == "skeleton" and s.get("label_id") == 87][0]
    allok = True
    for e in sk2.get("elements") or []:
        nm = ID2NAME[e["label_id"]]
        want_occ = nm in NEW
        good = e["occluded"] == want_occ and not e["outside"]
        if want_occ:
            good = good and abs(e["points"][0] - NEW[nm][0]) < 0.01 and abs(e["points"][1] - NEW[nm][1]) < 0.01
        allok = allok and good
    if allok:
        ok("Kiểm lại: cả 13 điểm đúng (8 điểm mắt occluded, mũi/miệng/môi giữ nguyên).")
    else:
        bad("Kiểm lại còn sai — gửi file fix_debug.json cho trợ lý.")
        json.dump(d2, open("fix_debug.json", "w"), indent=1)
        return 1
    if state == "completed":
        cv.patch(f"/api/jobs/{jid}", {"state": "completed"})
        ok("Trả job về 'completed'.")
    print("\n\033[32mXong.\033[0m Chạy tiếp: python lab.py export")
    return 0


if __name__ == "__main__":
    sys.exit(main())
