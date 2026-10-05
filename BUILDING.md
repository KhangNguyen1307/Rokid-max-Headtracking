# Chạy và đóng gói từ mã nguồn

**[English](BUILDING_EN.md) · Tiếng Việt**

Môi trường đã dùng: Windows x64, Python 3.12.14, các phiên bản trong `requirements-build.txt`. Máy chỉ dùng app tải về không cần Python.

## Chuẩn bị

Mở PowerShell trong thư mục mã nguồn:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

## Chạy

```powershell
.\.venv\Scripts\python.exe rokid_tracker.py
```

Mã nguồn dùng bản pystray 0.19.5 không sửa đổi trong `third_party/pystray`. Để sửa hoặc thay thế thư viện này, sửa các tệp tại đó rồi chạy / đóng gói lại; không có khóa hay kiểm tra chữ ký ngăn thay thế. Giữ giấy phép LGPL và thông báo tác giả của thư viện.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m unittest test_localization test_game_presence test_output_scheduler test_motion_filter test_connection test_event_console test_mouse_output
.\.venv\Scripts\python.exe rokid_tracker.py --self-check
.\.venv\Scripts\python.exe rokid_tracker.py --ui-check
.\.venv\Scripts\python.exe rokid_tracker.py --ui-check --ui-language en
```

`test_game_output` kiểm tra thư viện game thật và dùng vùng dữ liệu FreeTrack chung. Chỉ chạy khi Kariuss, OpenTrack và các game đang nhận head tracking đều đã đóng:

```powershell
.\.venv\Scripts\python.exe -m unittest test_game_output
```

`--ui-check` không đăng ký kết nối game, dùng thư mục tạm cho trạng thái / cài đặt và có thể đọc kính trong thời gian ngắn. Từ điển giao diện nằm trong `localization.py`; các giá trị lưu cho độ mượt / gán nút giữ nguyên khi đổi ngôn ngữ.

## Đóng gói

```powershell
.\.venv\Scripts\python.exe build_app.py
```

Kết quả nằm trong `releases/<phiên bản>/Kariuss Max Headtracking/`. Khi chia sẻ, nén cả thư mục này; không tách riêng `.exe` khỏi `_internal`.

Các thư viện client trong `game_clients/` là bản không sửa đổi của OpenTrack 2026.1.0. Mã NPClient đi kèm tại `game_clients/npclient/`; nguồn các thành phần còn lại và thông báo giấy phép ở `THIRD_PARTY.md`. Khi thay thư viện client, giữ tên, giao diện hàm và bố cục dữ liệu tương thích.

