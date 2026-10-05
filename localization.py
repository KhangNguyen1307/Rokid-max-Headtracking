# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
"""Presentation-only translations; saved tracking values remain language independent."""
import ctypes
import tkinter as tk
import weakref

LANGUAGES = {'vi': 'Tiếng Việt', 'en': 'English'}
ENGLISH = {
    'Reset chuột hoặc F8 trong Mouse Control: đưa con trỏ về giữa, đặt lại hướng kính và các góc về 0.': 'Reset mouse or F8 in Mouse Control: center the cursor and reset the glasses orientation and displayed angles to zero.',
    'Đã đưa chuột về giữa màn hình và đặt lại hướng đầu': 'Mouse moved to the screen center and head reference reset',
    'Reset chuột hoặc F8 trong Mouse Control: đưa chuột về giữa màn hình và đặt lại hướng đầu.': 'Reset mouse or F8 in Mouse Control: move the cursor to the screen center and reset the head reference.',
    'Trong góc đã chọn: chuột đi theo đầu. Vượt góc đó: giữ đầu lệch để quay liên tục.': 'Within the chosen angle: the mouse follows your head. Beyond it: hold your head turned for continuous turning.',
    'Góc bắt đầu là 180°: toàn bộ phạm vi vẫn điều khiển chuột theo đầu; không tự quay liên tục.': 'Start angle is 180°: the mouse follows your head throughout the full range, with no continuous turning.',
    'Trong góc bắt đầu: chuột đi theo đầu. Vượt góc đó: quay liên tục ở tốc độ tối đa.': 'Within the start angle: the mouse follows your head. Beyond it: turn continuously at maximum speed.',
    'Góc bắt đầu là 180°: chế độ quay liên tục sẽ không tự quay.': 'Start angle is 180°: continuous turning stays off.',
    'Góc tốc độ cao nhất không lớn hơn góc bắt đầu: vượt góc bắt đầu là quay tối đa; về giữa để dừng.': 'Maximum-speed angle is at or below the start angle: turn at full speed beyond the start angle; return to center to stop.',
    'Điều khiển chuột': 'Mouse control',
    'Đặt lại hướng đầu': 'Recenter head',
    'Đã đặt lại hướng đầu. Góc nhìn trong game được giữ nguyên.': 'Head recentered. The game view is unchanged.',
    'Chỉnh trong tab Điều khiển chuột': 'Adjust in the Mouse control tab',
    'Giữ phím để đưa đầu về giữa': 'Hold a key to recenter your head',
    'Giữ đầu lệch để quay liên tục': 'Hold your head turned for continuous turning',
    'Chọn kiểu điều khiển rồi bấm bắt đầu. Các thiết lập ở đây chỉ áp dụng cho chuột.': 'Choose a control style, then click start. These settings apply only to mouse control.',
    'Kiểu điều khiển:': 'Control style:',
    'Giữ đầu lệch sang bên để game quay liên tục. Đưa đầu về giữa để dừng quay.': 'Keep your head turned to make the game turn continuously. Return to center to stop turning.',
    'Quay đầu để ngắm. Khi cần đưa đầu về giữa, giữ phím đã chọn rồi thả ra để quay tiếp.': 'Turn your head to aim. To return your head to center, hold the chosen key, then release it to continue turning.',
    'Giữ để đưa đầu về giữa:': 'Hold to recenter your head:',
    'Nút phụ chuột 1': 'Mouse side button 1',
    'Nút phụ chuột 2': 'Mouse side button 2',
    'Giữ phím đã chọn: game không quay theo đầu. Thả phím: điều khiển tiếp từ tư thế mới.': 'Hold the chosen key: head movement stops controlling the game. Release: continue from your new head position.',
    'Chọn phím chưa dùng trong game; app không chặn chức năng gốc của phím.': 'Choose a key unused by your game; the app does not block the key from reaching the game.',
    'Quay liên tục': 'Continuous turning',
    'Bắt đầu quay khi lệch hơn:': 'Start turning beyond:',
    'Đạt tốc độ cao nhất ở:': 'Reach maximum speed at:',
    'Tốc độ quay tối đa:': 'Maximum turn speed:',
    'Ngẩng / cúi cũng quay liên tục': 'Also turn continuously up / down',
    'Chậm': 'Slow',
    'Bình thường': 'Normal',
    'Nhanh': 'Fast',
    'Rất nhanh': 'Very fast',
    'F8 hoặc nút reset trên kính: đặt tư thế đầu hiện tại làm hướng giữa, giữ nguyên góc nhìn game.': 'F8 or the glasses reset action: use your current head position as center, keeping the game view unchanged.',
    'Đã lưu thiết lập điều khiển chuột: ': 'Mouse control settings saved: ',
    'Đang giữ phím. Đưa đầu về giữa rồi thả phím để điều khiển tiếp.': 'Key held. Return your head to center, then release the key to continue.',
    'Chế độ chuột chưa được chọn.': 'Mouse control mode is not selected.',
    'Bấm để bắt đầu điều khiển chuột': 'Click to start mouse control',
    'Dừng điều khiển chuột': 'Stop mouse control',
    'Đã dừng điều khiển chuột': 'Mouse control stopped',
    'Chưa bắt đầu điều khiển chuột.': 'Mouse control has not started.',
    'Reset chuột': 'Reset mouse',
    'Độ mượt chuột:': 'Mouse smoothing:',
    'Độ nhạy chuột:': 'Mouse sensitivity:',
    'Đã chỉnh độ mượt chuột: ': 'Mouse smoothing set to: ',
    'Đã chọn chế độ: ': 'Selected mode: ',
    'Đã đưa chuột về giữa màn hình': 'Mouse moved to the center of the screen',
    'Không reset được chuột: ': 'Could not reset mouse: ',
    'Tạm dừng điều khiển chuột': 'Pause mouse control',
    'Tiếp tục điều khiển chuột': 'Resume mouse control',
    'Đã tạm dừng điều khiển chuột': 'Mouse control paused',
    'Đã tiếp tục điều khiển chuột': 'Mouse control resumed',
    'Đã bật điều khiển chuột. Chuyển sang game để sử dụng.': 'Mouse control enabled. Switch to your game to use it.',
    'Đang điều khiển chuột': 'Controlling mouse',
    'Đang chờ điều khiển chuột': 'Waiting for mouse control',
    'Điều khiển chuột đã bật. Chuyển sang game; chuột tạm dừng khi cửa sổ Kariuss ở phía trước.': 'Mouse control enabled. Switch to your game; mouse control pauses while the Kariuss window is in front.',
    'Windows không nhận chuyển động chuột. Kiểm tra quyền chạy của app và game.': 'Windows did not accept mouse movement. Check the app and game privileges.',
    'Không đọc được vị trí chuột.': 'Could not read the mouse position.',
    'Không xác định được màn hình của chuột.': 'Could not identify the mouse monitor.',
    'Không đưa được chuột về giữa màn hình.': 'Could not move the mouse to the screen center.',
    'Chọn chế độ trước khi kết nối game.': 'Select a mode before connecting to the game.',
    'Đặt trên mặt phẳng 6 giây để kính hiệu chỉnh': 'Place the glasses on a flat surface for 6 seconds to calibrate',
    'Giữ chức năng gốc': 'Keep original function',
    'Nhìn về giữa': 'Reset view',
    'Tạm dừng / tiếp tục nhìn theo đầu': 'Pause / resume head tracking',
    'Nút tăng âm lượng': 'Volume up button',
    'Nút giảm âm lượng': 'Volume down button',
    'Nút độ sáng': 'Brightness button',
    'Bấm tăng rồi giảm, hoặc giảm rồi tăng': 'Press volume up then down, or down then up',
    'Đang tìm kính…': 'Looking for glasses…',
    'Đang kết nối với kính…': 'Connecting to glasses…',
    'Đã ngắt kết nối. Bấm Kết nối để dùng lại.': 'Disconnected. Click Connect to use the glasses again.',
    'Đã ngắt kết nối. Bấm Kết nối kính để dùng lại.': 'Disconnected. Click Connect glasses to use them again.',
    'Chưa thấy kính. Cắm kính vào PC; app sẽ tự nhận.': 'No glasses found. Connect them to your PC; the app will detect them automatically.',
    'Mất kết nối với kính. Kiểm tra dây; app sẽ tự nhận lại.': 'Glasses disconnected. Check the cable; the app will reconnect automatically.',
    'Chưa nhận chuyển động từ kính. App đang thử kết nối lại…': 'No motion received from glasses. Retrying the connection…',
    'Đã nhận chuyển động': 'Motion detected',
    'Đang kết nối với kính': 'Connecting to glasses',
    'Đã ngắt kết nối với kính': 'Disconnected from glasses',
    'Ngắt kết nối': 'Disconnect',
    'Kết nối': 'Connect',
    'Kết nối kính': 'Connect glasses',
    'Đang tìm lại kết nối USB': 'Scanning for USB devices',
    'Tìm lại USB': 'Rescan USB',
    'Đã chọn thiết bị: ': 'Selected device: ',
    'Đang tìm kết nối USB của kính…': 'Looking for the glasses USB connection…',
    'Theo dõi chuyển động': 'Head tracking',
    'Nút trên kính': 'Glasses buttons',
    'Tắt': 'Off',
    'Mượt nhẹ': 'Light',
    'Mượt vừa': 'Medium',
    'Mượt nhiều': 'Strong',
    'Đã lưu chiều chuyển động: ': 'Saved axis directions: ',
    'trái/phải': 'left/right',
    'ngẩng/cúi': 'up/down',
    'nghiêng': 'tilt',
    ' đảo chiều': ' inverted',
    ' bình thường': ' normal',
    'Quay trái / phải': 'Turn left / right',
    'Ngẩng / cúi': 'Look up / down',
    'Nghiêng đầu': 'Tilt head',
    'Đảo chiều': 'Invert',
    'Chưa bấm nút điều khiển.': 'No control button pressed yet.',
    'Kính chưa sẵn sàng. Chờ nhận chuyển động rồi thử lại.': 'Glasses are not ready. Wait for motion detection, then try again.',
    'Đã reset góc nhìn': 'View reset',
    'Đã tạm dừng theo dõi đầu trong game': 'Head tracking paused in game',
    'Đã tiếp tục theo dõi đầu': 'Head tracking resumed',
    'Tiếp tục theo dõi đầu': 'Resume head tracking',
    'Tạm dừng theo dõi đầu': 'Pause head tracking',
    'Reset góc nhìn': 'Reset view',
    'Đã bật kết nối game trực tiếp. Mở game để sử dụng.': 'Game connection enabled. Open your game to use head tracking.',
    'Đã tắt kết nối với game': 'Game connection disabled',
    'Không bật được kết nối game: ': 'Could not enable game connection: ',
    'Kết nối game': 'Connect to game',
    'Chưa bật kết nối với game.': 'Game connection is disabled.',
    'Tần số gửi:': 'Output rate:',
    'Đã chọn tần số gửi: ': 'Selected output rate: ',
    'Độ mượt:': 'Smoothing:',
    'Độ nhạy:': 'Sensitivity:',
    'Đã chỉnh độ mượt: ': 'Smoothing set to: ',
    '; độ nhạy: ': '; sensitivity: ',
    'Chọn thêm việc app làm khi bạn bấm nút.': 'Choose an extra app action for each glasses button.',
    'Đã gán bấm đôi âm lượng: ': 'Volume button pair assigned: ',
    'Đã gán ': 'Assigned ',
    'nút tăng âm lượng': 'volume up button',
    'nút giảm âm lượng': 'volume down button',
    'nút độ sáng': 'brightness button',
    'Hai lần bấm âm lượng ngược nhau trong 0,8 giây:': 'Two opposite volume presses within 0.8 seconds:',
    'Để giữ độ sáng: dùng hai lần bấm âm lượng ở trên, hoặc F8. Âm lượng đổi tạm rồi trở lại mức ban đầu.': 'To keep brightness unchanged, use the volume button pair above or F8. Volume changes briefly, then returns to its original level.',
    'App chưa chặn được chức năng gốc: nút độ sáng vẫn đổi độ sáng; nút âm lượng vẫn đổi âm lượng. Ở mức âm lượng cao nhất, bấm giảm rồi tăng; ở mức thấp nhất, bấm tăng rồi giảm.': 'The original button functions still apply: brightness and volume will still change. At maximum volume, press down then up; at minimum volume, press up then down.',
    'Đang chờ kính…': 'Waiting for glasses…',
    'Đã mở Kariuss Max Headtracking': 'Kariuss Max Headtracking opened',
    'Đã mở lại cửa sổ': 'Window reopened',
    'Đã chuyển app sang chạy ngầm': 'App moved to the system tray',
    'Biểu tượng cạnh đồng hồ chưa sẵn sàng; app được thu xuống thanh tác vụ.': 'System tray icon is not ready; the app was minimized to the taskbar.',
    'OpenTrack đang mở. Tắt OpenTrack rồi bật lại Kết nối với game.': 'OpenTrack is running. Close it, then enable the game connection again.',
    'Thiết bị đã chọn chưa kết nối': 'Selected device is not connected',
    'Tìm thấy ': 'Found ',
    ' kính qua USB.': ' glasses via USB.',
    'Chưa phát hiện kính': 'No glasses detected',
    'Chưa thấy kính qua USB. Cắm dây hoặc bấm Tìm lại USB.': 'No glasses found via USB. Connect the cable or click Rescan USB.',
    'Đang theo dõi · tạm dừng gửi': 'Tracking · output paused',
    'Đang theo dõi đầu': 'Tracking head movement',
    'Đang hiệu chỉnh kính…': 'Calibrating glasses…',
    'Đã ngắt kết nối': 'Disconnected',
    'Kết nối game bị gián đoạn: ': 'Game connection interrupted: ',
    'Game đã nhận kết nối Kariuss: ': 'Game connected to Kariuss: ',
    'Game đã ngắt kết nối Kariuss': 'Game disconnected from Kariuss',
    'Game đã nhận kết nối: ': 'Game connected: ',
    'Chưa có game kết nối. Mở game và vào buồng lái.': 'No game connected. Open your game and enter the cockpit.',
    'Đang tạm dừng theo dõi đầu.': 'Head tracking is paused.',
    'Đang gửi hướng nhìn.': 'Sending view direction.',
    'Chưa gửi hướng nhìn.': 'View output is inactive.',
    'Đã nhận nút kính. Các lựa chọn được lưu tự động.': 'Glasses buttons detected. Your settings are saved automatically.',
    'Chờ kính sẵn sàng rồi bấm nút để thử.': 'Wait for the glasses to be ready, then press a button to test.',
    ' — đang chạy': ' — running',
    ' — chưa kết nối': ' — disconnected',
    'Đã thoát Kariuss Max Headtracking': 'Kariuss Max Headtracking closed',
    'Kính đã sẵn sàng theo dõi đầu': 'Glasses are ready for head tracking',
    'Mất kết nối với kính. Đang tự kết nối lại': 'Glasses disconnected. Reconnecting automatically',
    'Nhật ký hoạt động': 'Activity log',
    'Thoát hẳn': 'Quit app',
    'Đã kết nối với kính Rokid Max': 'Connected to Rokid Max glasses',
    'Kết nối / Ngắt kết nối': 'Connect / disconnect',
    'Mở cửa sổ': 'Open window',
    'Tạm dừng / tiếp tục': 'Pause / resume',
    'Chưa kết nối kính': 'Glasses not connected',
    'Đang chờ kính sẵn sàng': 'Waiting for glasses to be ready',
    'Hãy tắt OpenTrack trước khi bật kết nối game trong Kariuss.': 'Close OpenTrack before enabling the game connection in Kariuss.',
    'Không đọc được bản lưu kết nối game. Chưa thay đổi cài đặt Windows.': 'Could not read the saved game connection state. Windows settings have not been changed.',
    'Thiếu thành phần kết nối game: ': 'Missing game connection component: ',
    'Đã có một Kariuss khác gửi chuyển động vào game.': 'Another Kariuss instance is already sending motion to the game.',
    'Đã đổi ngôn ngữ: ': 'Language changed to: ',
}


def default_language(preferences, windows_language=None):
    saved = preferences.get('language')
    if saved in LANGUAGES:
        return saved
    # Preserve Vietnamese for existing users upgrading from the first release.
    if preferences:
        return 'vi'
    if windows_language is None:
        try:
            windows_language = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        except AttributeError:
            windows_language = 0
    return 'vi' if windows_language & 0x3ff == 0x2a else 'en'


class Translator:
    def __init__(self, language='vi'):
        self.language = language
        self.refreshing = False
        self.variables = []
        self.reverse = {value: key for key, value in ENGLISH.items()}
        # Longer messages must be translated before their constituent phrases.
        self.replacements = sorted(ENGLISH.items(), key=lambda pair: len(pair[0]), reverse=True)

    def tr(self, text):
        if self.language == 'vi':
            return text
        if text in ENGLISH:
            return ENGLISH[text]
        for original, translated in self.replacements:
            text = text.replace(original, translated)
        return text

    def canonical(self, text):
        return self.reverse.get(text, text)

    def set_language(self, language):
        if language not in LANGUAGES:
            raise ValueError('Unsupported language')
        # Read before changing language, including values set directly by Tk.
        variables = [reference() for reference in self.variables]
        values = [(variable, variable.get()) for variable in variables if variable is not None]
        self.language = language
        self.refreshing = True
        try:
            for variable, value in values:
                variable.set(value)
        finally:
            self.refreshing = False


class TranslatedStringVar(tk.StringVar):
    """Tk displays translated text; application code gets stable original values."""
    def __init__(self, translator, *args, **kwargs):
        self.translator = translator
        self.original = kwargs.get('value', '')
        kwargs['value'] = translator.tr(self.original)
        super().__init__(*args, **kwargs)
        translator.variables.append(weakref.ref(self))

    def get(self):
        displayed = super().get()
        if displayed == self.translator.tr(self.original):
            return self.original
        return self.translator.canonical(displayed)

    def set(self, value):
        self.original = value
        super().set(self.translator.tr(value))
