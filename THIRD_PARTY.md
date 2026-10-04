# Thành phần và giấy phép bên thứ ba

**[English](THIRD_PARTY_EN.md) · Tiếng Việt**

Giấy phép GPL-3.0 của Kariuss không thay thế giấy phép riêng của những thành phần bên dưới. Các bản phát hành chứa thông báo này và thư mục `licenses/`.

| Thành phần | Phiên bản / nguồn | Giấy phép và nơi ghi nhận |
|---|---|---|
| Cách làm mượt Accela, đường phản hồi spline | Chuyển sang Python từ OpenTrack; Stanislaw Halik, 2012–2019 | Thông báo cho phép sử dụng / sửa / phân phối và miễn bảo hành giữ trong `motion_filter.py`, `game_clients/README-KARIUSS.txt` |
| NPClient32/64, FreeTrack32/64, TrackIR helper, danh sách game | Không sửa đổi, từ OpenTrack 2026.1.0 | `game_clients/OPENTRACK-LICENSING.txt`, `FACETRACKNOIR-COPYING.txt`; dự án nguồn https://github.com/opentrack/opentrack |
| NPClient / linuxtrack | Nguồn trong `game_clients/npclient/`; Tulthix, uglyDwarf | MIT; `licenses/linuxtrack-MIT.txt`; https://github.com/uglyDwarf/linuxtrack |
| pystray | 0.19.5; nguồn không sửa đổi đi kèm tại `third_party/pystray/` | LGPL-3.0-or-later; `licenses/pystray-LGPL-3.0.txt` và `licenses/GPL-3.0.txt`; https://github.com/moses-palmer/pystray/tree/v0.19.5 |
| VQF | 2.1.2 | MIT; `licenses/vqf-LICENSE.txt`; https://github.com/dlaidig/vqf |
| cython-hidapi / HIDAPI | 0.15.0 | Chọn giấy phép BSD / giấy phép gốc cho thành phần này; thông báo và lựa chọn khác trong `licenses/hidapi-*.txt`; https://github.com/trezor/cython-hidapi |
| NumPy | 2.3.5 | BSD và thông báo cho các thư viện đi kèm; `licenses/numpy-LICENSE.txt`; https://github.com/numpy/numpy |
| Pillow | 12.3.0 | Giấy phép HPND / PIL và các thành phần đi kèm; `licenses/Pillow-LICENSE*`; https://github.com/python-pillow/Pillow |
| six | 1.17.0 | MIT; `licenses/six-LICENSE`; https://github.com/benjaminp/six |
| Python và Tcl/Tk | Runtime Python 3.12 | Giấy phép runtime trong `licenses/` và `_internal/_tcl_data/license.terms`, `_internal/_tk_data/license.terms` khi đóng gói |
| PyInstaller bootloader | 6.22.0 | GPL cùng ngoại lệ bootloader; `licenses/pyinstaller-COPYING.txt`; https://github.com/pyinstaller/pyinstaller |

Mã nguồn Kariuss, hướng dẫn đóng gói và pystray đi kèm cho phép tạo lại app với bản thư viện đã sửa. Các phụ thuộc còn lại có phiên bản xác định trong `requirements*.txt`; nguồn chính thức được dẫn ở bảng trên.

Bố cục gói dữ liệu Rokid được tham khảo từ https://github.com/badicsalex/ar-drivers-rs/blob/master/src/rokid.rs. Cách hợp nhất chuyển động dùng thư viện VQF; không chép mã firmware HeadTracker vào app. Các mức gửi FPV được tham khảo từ https://github.com/headtracker/HeadTracker.

Kariuss là dự án cộng đồng, không khẳng định được Rokid, OpenTrack hoặc Microsoft chứng nhận.

