# -*- coding: utf-8 -*-
# light_calc_full_mobile.py 完整Kivy手机版：伪装计算器私密相册
# 完整功能：计算器伪装、主相册、多级文件夹、子分相册、赞助入口、修改主密码、7次点击标题唤起管理员菜单
# 已适配 Android（buildozer 打包）：权限动态申请、应用私有目录存储、中文字体适配、文件选择器适配
import os
import sys
import base64
import hashlib
import sqlite3
import time
from datetime import datetime

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image as KivyImage
from kivy.core.window import Window
from kivy.uix.filechooser import FileChooserListView
from kivy.core.text import LabelBase
from PIL import Image
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

# ===================== 平台判断 =====================
IS_ANDROID = False
if "ANDROID_ARGUMENT" in os.environ:
    IS_ANDROID = True

# ===================== Android 权限申请（启动即请求） =====================
if IS_ANDROID:
    try:
        from android.permissions import request_permissions, Permission
        from android.storage import app_storage_path, primary_external_storage_path
        # 动态申请存储权限（Android 6.0+ 必须运行时申请）
        request_permissions([
            Permission.READ_EXTERNAL_STORAGE,
            Permission.WRITE_EXTERNAL_STORAGE,
            Permission.READ_MEDIA_IMAGES,
        ])
    except Exception as e:
        print(f"[权限] 申请异常（可忽略，进入App后系统会再次弹框）：{e}")

# ===================== 中文字体注册（Android 兼容） =====================
_CJK_FONT_CANDIDATES = [
    # Android 系统字体（最优先，几乎所有机型都有）
    "/system/fonts/NotoSansCJK-Regular.ttc",
    "/system/fonts/DroidSansFallbackFull.ttf",
    "/system/fonts/DroidSansFallback.ttf",
    "/system/fonts/SourceHanSansCN-Regular.otf",
    "/system/fonts/Roboto-Regular.ttf",
    # Windows
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    # Linux
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    # 打包进APK的字体（如果放了的话）
    "msyh.ttc",
    "simhei.ttf",
    "NotoSansCJK-Regular.ttc",
]

def _register_cjk_font():
    for path in _CJK_FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                LabelBase.register(name="Roboto", fn_regular=path)
                print(f"[字体] 已加载中文字体: {path}")
                return
            except Exception as e:
                print(f"[字体] 加载失败 {path}: {e}")
    print("[字体] 未找到中文字体，中文可能显示为方块")

_register_cjk_font()

APP_NAME = "轻计算器"

# ===================== 应用数据目录（Android 适配） =====================
# Android 上使用 App 自身的私有外部存储，无需存储权限即可读写；
# 加密后的图片、数据库都放在这里，卸载App时自动清除。
if IS_ANDROID:
    try:
        from android.storage import app_storage_path
        BASE_DIR = app_storage_path()
    except Exception:
        BASE_DIR = os.path.join(os.path.expanduser("~"), ".light_calculator_mobile")
else:
    BASE_DIR = os.path.join(os.path.expanduser("~"), ".light_calculator_mobile")

VAULT_DIR = os.path.join(BASE_DIR, "vault")
DB_PATH = os.path.join(BASE_DIR, "data.db")
MK_FILE = os.path.join(BASE_DIR, "master_key.enc")
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(VAULT_DIR, exist_ok=True)
print(f"[路径] 数据目录: {BASE_DIR}")

# ===================== 加密工具 =====================
def pbkdf2(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000, dklen=32)

def hash_password(password: str, salt: bytes) -> str:
    return base64.b64encode(pbkdf2(password, salt)).decode()

def get_random_salt() -> bytes:
    return get_random_bytes(16)

def aes_encrypt(key: bytes, data: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_GCM)
    ct, tag = cipher.encrypt_and_digest(data)
    return cipher.nonce + tag + ct

def aes_decrypt(key: bytes, raw: bytes) -> bytes:
    nonce, tag, ct = raw[:16], raw[16:32], raw[32:]
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ct, tag)

def encrypt_file(src_path, dst_path, key):
    with open(src_path, "rb") as f:
        data = f.read()
    with open(dst_path, "wb") as f:
        f.write(aes_encrypt(key, data))

def decrypt_file(src_path, dst_path, key):
    with open(src_path, "rb") as f:
        raw = f.read()
    with open(dst_path, "wb") as f:
        f.write(aes_decrypt(key, raw))

def wrap_master_key(mk: bytes, k1: bytes):
    with open(MK_FILE, "wb") as f:
        f.write(aes_encrypt(k1, mk))

def unwrap_master_key(k1: bytes) -> bytes:
    with open(MK_FILE, "rb") as f:
        raw = f.read()
    return aes_decrypt(k1, raw)

# ===================== 数据库 =====================
class DB:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.init_tables()

    def init_tables(self):
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS vaults (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                pass_hash TEXT,
                salt TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vault_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                parent_id INTEGER,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vault_id INTEGER NOT NULL,
                folder_id INTEGER,
                filename TEXT NOT NULL,
                enc_path TEXT NOT NULL,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS amount_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount_hash TEXT NOT NULL,
                vault_id INTEGER NOT NULL
            )
        """)
        self.conn.commit()

    def has_main_vault(self):
        c = self.conn.cursor()
        c.execute("SELECT id FROM vaults WHERE type='main' LIMIT 1")
        return c.fetchone() is not None

    def create_main_vault(self, password):
        salt = get_random_salt()
        pwd_hash = hash_password(password, salt)
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO vaults (name, type, pass_hash, salt, created_at) VALUES (?,?,?,?,?)",
            ("主相册", "main", pwd_hash,
             base64.b64encode(salt).decode(), datetime.now().isoformat())
        )
        self.conn.commit()
        return c.lastrowid

    def get_main_vault_row(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM vaults WHERE type='main' LIMIT 1")
        return c.fetchone()

    def verify_main_password(self, password):
        row = self.get_main_vault_row()
        if not row:
            return None
        salt = base64.b64decode(row["salt"])
        return row["id"] if hash_password(password, salt) == row["pass_hash"] else None

    def update_main_password(self, new_password):
        salt = get_random_salt()
        pwd_hash = hash_password(new_password, salt)
        c = self.conn.cursor()
        c.execute("UPDATE vaults SET pass_hash=?, salt=? WHERE type='main'",
                  (pwd_hash, base64.b64encode(salt).decode()))
        self.conn.commit()
        return salt

    def get_vault(self, vault_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM vaults WHERE id=?", (vault_id,))
        return c.fetchone()

    def get_folders(self, vault_id, parent_id=None):
        c = self.conn.cursor()
        if parent_id is None:
            c.execute("SELECT * FROM folders WHERE vault_id=? AND parent_id IS NULL ORDER BY name", (vault_id,))
        else:
            c.execute("SELECT * FROM folders WHERE vault_id=? AND parent_id=? ORDER BY name", (vault_id, parent_id))
        return c.fetchall()

    def get_photos(self, vault_id, folder_id=None):
        c = self.conn.cursor()
        if folder_id is None:
            c.execute("SELECT * FROM photos WHERE vault_id=? AND folder_id IS NULL ORDER BY created_at DESC", (vault_id,))
        else:
            c.execute("SELECT * FROM photos WHERE vault_id=? AND folder_id=? ORDER BY created_at DESC", (vault_id, folder_id))
        return c.fetchall()

    def add_folder(self, vault_id, name, parent_id=None):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO folders (vault_id, name, parent_id, created_at) VALUES (?,?,?,?)",
            (vault_id, name, parent_id, datetime.now().isoformat())
        )
        self.conn.commit()
        return c.lastrowid

    def add_photo(self, vault_id, folder_id, filename, enc_path):
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO photos (vault_id, folder_id, filename, enc_path, created_at) VALUES (?,?,?,?,?)",
            (vault_id, folder_id, filename, enc_path, datetime.now().isoformat())
        )
        self.conn.commit()
        return c.lastrowid

    def delete_photo(self, photo_id):
        c = self.conn.cursor()
        c.execute("SELECT enc_path FROM photos WHERE id=?", (photo_id,))
        row = c.fetchone()
        if row and os.path.exists(row["enc_path"]):
            os.remove(row["enc_path"])
        c.execute("DELETE FROM photos WHERE id=?", (photo_id,))
        self.conn.commit()

    def delete_folder(self, folder_id):
        c = self.conn.cursor()
        c.execute("SELECT id FROM folders WHERE parent_id=?", (folder_id,))
        for sub in c.fetchall():
            self.delete_folder(sub["id"])
        c.execute("SELECT id FROM photos WHERE folder_id=?", (folder_id,))
        for p in c.fetchall():
            self.delete_photo(p["id"])
        c.execute("DELETE FROM folders WHERE id=?", (folder_id,))
        self.conn.commit()

    def get_all_sub_vaults(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM vaults WHERE type='sub' ORDER BY id")
        return c.fetchall()

    def is_amount_used(self, amount):
        amount_hash = hashlib.sha256(str(amount).encode()).hexdigest()
        c = self.conn.cursor()
        c.execute("SELECT id FROM amount_map WHERE amount_hash=?", (amount_hash,))
        return c.fetchone() is not None

    def create_sub_vault_custom(self, name, amount):
        if self.is_amount_used(amount):
            return None, "该金额已被使用"
        salt = get_random_salt()
        pwd_hash = hash_password(amount, salt)
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO vaults (name, type, pass_hash, salt, created_at) VALUES (?,?,?,?,?)",
            (name, "sub", pwd_hash,
             base64.b64encode(salt).decode(), datetime.now().isoformat())
        )
        vault_id = c.lastrowid
        amount_hash = hashlib.sha256(str(amount).encode()).hexdigest()
        c.execute("INSERT INTO amount_map (amount_hash, vault_id) VALUES (?,?)",
                  (amount_hash, vault_id))
        self.conn.commit()
        return vault_id, None

    def update_sub_vault_amount(self, vault_id, new_amount):
        if self.is_amount_used(new_amount):
            return False, "该金额已被使用"
        amount_hash = hashlib.sha256(str(new_amount).encode()).hexdigest()
        c = self.conn.cursor()
        c.execute("UPDATE amount_map SET amount_hash=? WHERE vault_id=?",
                  (amount_hash, vault_id))
        self.conn.commit()
        return True, None

    def update_sub_vault_name(self, vault_id, new_name):
        c = self.conn.cursor()
        c.execute("UPDATE vaults SET name=? WHERE id=?", (new_name, vault_id))
        self.conn.commit()

    def delete_sub_vault(self, vault_id):
        c = self.conn.cursor()
        c.execute("SELECT enc_path FROM photos WHERE vault_id=?", (vault_id,))
        for row in c.fetchall():
            if os.path.exists(row["enc_path"]):
                os.remove(row["enc_path"])
        c.execute("DELETE FROM photos WHERE vault_id=?", (vault_id,))
        c.execute("DELETE FROM folders WHERE vault_id=?", (vault_id,))
        c.execute("DELETE FROM amount_map WHERE vault_id=?", (vault_id,))
        c.execute("DELETE FROM vaults WHERE id=?", (vault_id,))
        self.conn.commit()

    def find_vault_by_amount(self, amount):
        amount_hash = hashlib.sha256(str(amount).encode()).hexdigest()
        c = self.conn.cursor()
        c.execute("SELECT vault_id FROM amount_map WHERE amount_hash=?", (amount_hash,))
        row = c.fetchone()
        return row["vault_id"] if row else None

    def close(self):
        self.conn.close()

# ===================== 获取文件选择器起始目录（Android 兼容） =====================
def get_pictures_start_dir():
    """返回一个适合 FileChooserListView 打开的目录"""
    candidates = []
    if IS_ANDROID:
        try:
            from android.storage import primary_external_storage_path
            candidates.append(os.path.join(primary_external_storage_path(), "Pictures"))
            candidates.append(os.path.join(primary_external_storage_path(), "DCIM"))
            candidates.append(primary_external_storage_path())
        except Exception:
            pass
    candidates.append(os.path.expanduser("~"))
    for p in candidates:
        if os.path.exists(p) and os.path.isdir(p):
            return p
    return "/"

# ===================== Kivy 完整UI层 =====================
class LightCalcMobileApp(App):
    def build(self):
        self.title = APP_NAME
        Window.softinput_mode = "below_target"
        self.db = DB()
        self.current_vault_id = None
        self.current_folder_id = None
        self.master_key = None
        self.folder_stack = []
        self._title_click_count = 0
        self._title_last_click_time = 0
        self.main_layout = BoxLayout(orientation="vertical")
        self.show_calculator_screen()
        return self.main_layout

    def clear_layout(self):
        self.main_layout.clear_widgets()

    # --------计算器界面--------
    def show_calculator_screen(self):
        self.clear_layout()
        self.expr = ""
        top_label = Label(text=APP_NAME, font_size=24, size_hint_y=0.12)
        self.display_label = Label(text="0", font_size=42, size_hint_y=0.18, halign="right")
        self.main_layout.add_widget(top_label)
        self.main_layout.add_widget(self.display_label)

        grid = GridLayout(cols=4, size_hint_y=0.7)
        buttons = [
            "7","8","9","÷",
            "4","5","6","×",
            "1","2","3","-",
            "0",".","=","+",
            "AC","←"," "," "
        ]
        for t in buttons:
            if t == " ":
                continue
            btn = Button(text=t, font_size=22)
            btn.bind(on_press=lambda x,text=t:self.on_calc_btn(text))
            grid.add_widget(btn)
        self.main_layout.add_widget(grid)

    def on_calc_btn(self, text):
        if text == "AC":
            self.expr = ""
            self.display_label.text = "0"
        elif text == "←":
            self.expr = self.expr[:-1]
            self.display_label.text = self.expr if self.expr else "0"
        elif text == "=":
            self.handle_equal()
        elif text in "÷×-+":
            if self.expr and self.expr[-1] not in "÷×-+":
                self.expr += text
                self.display_label.text = self.expr
        else:
            self.expr += text
            self.display_label.text = self.expr

    def handle_equal(self):
        raw = self.expr.strip()
        if not raw:
            return
        if not self.db.has_main_vault():
            if raw.isdigit():
                vault_id = self.db.create_main_vault(raw)
                self.current_vault_id = vault_id
                mk = get_random_bytes(32)
                salt = base64.b64decode(self.db.get_main_vault_row()["salt"])
                k1 = pbkdf2(raw, salt)
                wrap_master_key(mk, k1)
                self.master_key = mk
                self.show_vault_ui(is_main=True)
            else:
                self.display_label.text = "错误"
            return
        vault_id = self.db.verify_main_password(raw)
        if vault_id:
            self.current_vault_id = vault_id
            salt = base64.b64decode(self.db.get_main_vault_row()["salt"])
            k1 = pbkdf2(raw, salt)
            try:
                self.master_key = unwrap_master_key(k1)
                self.show_vault_ui(is_main=True)
            except Exception:
                self.popup_msg("错误","主密钥解包失败，数据损坏")
                self.display_label.text = "错误"
        else:
            try:
                s = raw.replace("÷","/").replace("×","*")
                res = eval(s)
                self.display_label.text = str(res)
            except Exception:
                self.display_label.text = "错误"
            self.expr = ""

    def popup_msg(self, title, msg, callback=None):
        box = BoxLayout(orientation="vertical", padding=10)
        box.add_widget(Label(text=msg, font_size=14))
        btn = Button(text="确定", size_hint_y=None, height=48)
        popup = Popup(title=title, content=box, size_hint=(0.85,0.4))
        def dismiss_cb(x):
            popup.dismiss()
            if callback:
                callback()
        btn.bind(on_press=dismiss_cb)
        box.add_widget(btn)
        popup.open()
        return popup

    # --------相册界面--------
    def show_vault_ui(self, is_main=True):
        self.clear_layout()
        vault = self.db.get_vault(self.current_vault_id)
        self.current_folder_id = None
        self.folder_stack = []

        top_bar = BoxLayout(size_hint_y=0.12)
        back_btn = Button(text="←返回", font_size=14)
        if is_main:
            back_btn.bind(on_press=lambda x:self.smart_back())
        else:
            back_btn.bind(on_press=lambda x:self.show_vault_ui(is_main=True))
        top_bar.add_widget(back_btn)

        self.title_vault_label = Label(text=vault["name"], font_size=18)
        if is_main:
            self.title_vault_label.bind(on_touch_down=self.on_title_click_touch)
        top_bar.add_widget(self.title_vault_label)

        add_btn = Button(text="+", font_size=24)
        add_btn.bind(on_press=lambda x:self.show_vault_add_menu())
        top_bar.add_widget(add_btn)
        self.main_layout.add_widget(top_bar)

        action_bar = BoxLayout(size_hint_y=0.1, spacing=4)
        btn_new_folder = Button(text="新建文件夹", font_size=13)
        btn_new_folder.bind(on_press=lambda x:self.dialog_new_folder())
        btn_import = Button(text="导入图片", font_size=13)
        btn_import.bind(on_press=lambda x:self.import_image())
        btn_sponsor = Button(text="赞助作者", font_size=13, background_color=(1,0.4,0.4,1))
        btn_sponsor.bind(on_press=lambda x:self.show_sponsor_dialog())
        action_bar.add_widget(btn_new_folder)
        action_bar.add_widget(btn_import)
        action_bar.add_widget(btn_sponsor)
        self.main_layout.add_widget(action_bar)

        scroll = ScrollView()
        self.grid_content = GridLayout(cols=3, spacing=6, size_hint_y=None)
        self.grid_content.bind(minimum_height=self.grid_content.setter('height'))
        scroll.add_widget(self.grid_content)
        self.main_layout.add_widget(scroll)
        self.refresh_gallery_content()

    def on_title_click_touch(self, inst, touch):
        if inst.collide_point(*touch.pos):
            now = time.time()
            if now - self._title_last_click_time > 1.0:
                self._title_click_count = 0
            self._title_click_count += 1
            self._title_last_click_time = now
            if self._title_click_count >= 7:
                self._title_click_count = 0
                self.show_admin_menu_popup()

    def smart_back(self):
        if self.folder_stack:
            self.go_up_folder()
        else:
            self.show_calculator_screen()

    def go_up_folder(self):
        if self.folder_stack:
            self.folder_stack.pop()
        if self.folder_stack:
            self.current_folder_id = self.folder_stack[-1][0]
        else:
            self.current_folder_id = None
        self.update_gallery_title()
        self.refresh_gallery_content()

    def update_gallery_title(self):
        vault = self.db.get_vault(self.current_vault_id)
        if not self.folder_stack:
            self.title_vault_label.text = vault["name"]
        else:
            path = "/".join([i[1] for i in self.folder_stack])
            self.title_vault_label.text = f"{vault['name']}/{path}"

    def refresh_gallery_content(self):
        self.grid_content.clear_widgets()
        fid = self.current_folder_id
        vault_id = self.current_vault_id
        folders = self.db.get_folders(vault_id, fid)
        photos = self.db.get_photos(vault_id, fid)
        for fo in folders:
            b = Button(text=f"📁\n{fo['name']}", font_size=14, size_hint_y=None, height=130)
            b.bind(on_press=lambda x,fid=fo["id"],fn=fo["name"]:self.open_sub_folder(fid,fn))
            self.grid_content.add_widget(b)
        for ph in photos:
            b = Button(text=f"🖼️\n{ph['filename'][:8]}", font_size=12, size_hint_y=None, height=130)
            b.bind(on_press=lambda x,pid=ph["id"]:self.view_photo_pop(pid))
            self.grid_content.add_widget(b)

    def open_sub_folder(self, folder_id, folder_name):
        self.folder_stack.append((folder_id, folder_name))
        self.current_folder_id = folder_id
        self.update_gallery_title()
        self.refresh_gallery_content()

    def dialog_new_folder(self):
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        ti = TextInput(hint_text="输入文件夹名字", size_hint_y=None, height=48)
        box.add_widget(ti)
        def ok_func(x):
            name = ti.text.strip()
            if name:
                self.db.add_folder(self.current_vault_id, name, self.current_folder_id)
                self.refresh_gallery_content()
            popup.dismiss()
        btn_ok = Button(text="确定", size_hint_y=None, height=48)
        btn_ok.bind(on_press=ok_func)
        box.add_widget(btn_ok)
        popup = Popup(title="新建文件夹", content=box, size_hint=(0.85,0.35))
        popup.open()

    def import_image(self):
        content = BoxLayout(orientation="vertical")
        start_dir = get_pictures_start_dir()
        file_chooser = FileChooserListView(path=start_dir, filters=["*.png","*.jpg","*.jpeg","*.gif","*.bmp","*.webp"])
        def select_ok(x):
            selected = file_chooser.selection
            if not selected:
                self.popup_msg("提示","请先选择图片")
                return
            success = 0
            for src in selected:
                try:
                    fn = os.path.basename(src)
                    enc_name = f"{int(time.time()*1000)}_{fn}.enc"
                    enc_path = os.path.join(VAULT_DIR, enc_name)
                    encrypt_file(src, enc_path, self.master_key)
                    self.db.add_photo(self.current_vault_id, self.current_folder_id, fn, enc_path)
                    success += 1
                except Exception as e:
                    print(f"[导入] 失败 {src}: {e}")
            popup.dismiss()
            self.refresh_gallery_content()
            self.popup_msg("导入完成", f"成功导入 {success} 张图片")
        btn = Button(text="导入选中", size_hint_y=None, height=48)
        btn.bind(on_press=select_ok)
        content.add_widget(file_chooser)
        content.add_widget(btn)
        popup = Popup(title="选择图片", content=content, size_hint=(0.95,0.9))
        popup.open()

    def view_photo_pop(self, photo_id):
        cur = self.db.conn.cursor()
        cur.execute("SELECT * FROM photos WHERE id=?", (photo_id,))
        ph = cur.fetchone()
        if not ph:
            return
        tmp = os.path.join(BASE_DIR, "tmp_view.jpg")
        try:
            decrypt_file(ph["enc_path"], tmp, self.master_key)
        except Exception as e:
            self.popup_msg("错误", f"解密失败：{e}")
            return
        box = BoxLayout(orientation="vertical")
        img = KivyImage(source=tmp, allow_stretch=True)
        box.add_widget(img)
        close_btn = Button(text="关闭", size_hint_y=None, height=48)
        pop = Popup(title=ph["filename"], content=box, size_hint=(0.95,0.9))
        close_btn.bind(on_press=pop.dismiss)
        box.add_widget(close_btn)
        pop.open()

    def show_vault_add_menu(self):
        self.dialog_new_folder()

    # ========== 赞助弹窗 ==========
    def show_sponsor_dialog(self):
        box = BoxLayout(orientation="vertical", padding=12, spacing=10)
        box.add_widget(Label(text="赞助作者", font_size=18))
        box.add_widget(Label(text="请输入金额（数字）：", font_size=14))
        ti = TextInput(hint_text="纯数字", size_hint_y=None, height=48)
        box.add_widget(ti)
        btn_bar = BoxLayout(spacing=10, size_hint_y=None, height=48)
        pop = Popup(title="赞助作者", content=box, size_hint=(0.85,0.45))
        def on_cancel(x):
            pop.dismiss()
        def on_confirm(x):
            amount = ti.text.strip()
            pop.dismiss()
            if not amount.isdigit():
                self.popup_msg("提示","请输入纯数字金额")
                return
            sub_vid = self.db.find_vault_by_amount(amount)
            if sub_vid:
                vault = self.db.get_vault(sub_vid)
                self.current_vault_id = sub_vid
                self.show_vault_ui(is_main=False)
            else:
                self.show_fake_sponsor_page()
        btn_cancel = Button(text="取消")
        btn_ok = Button(text="确认赞助", background_color=(1,0.3,0.3,1))
        btn_cancel.bind(on_press=on_cancel)
        btn_ok.bind(on_press=on_confirm)
        btn_bar.add_widget(btn_cancel)
        btn_bar.add_widget(btn_ok)
        box.add_widget(btn_bar)
        pop.open()

    def show_fake_sponsor_page(self):
        box = BoxLayout(orientation="vertical", padding=12, spacing=15)
        box.add_widget(Label(text="赞助成功", font_size=20))
        box.add_widget(Label(text="感谢您的支持！\n作者会继续努力 ❤️", font_size=14))
        btn = Button(text="返回", size_hint_y=None, height=48)
        pop = Popup(title="赞助成功", content=box, size_hint=(0.8,0.4))
        btn.bind(on_press=pop.dismiss)
        box.add_widget(btn)
        pop.open()

    # ========== 管理员菜单 ==========
    def show_admin_menu_popup(self):
        box = BoxLayout(orientation="vertical", padding=12, spacing=12)
        pop = Popup(title="管理员菜单", content=box, size_hint=(0.85,0.42))
        btn_sub = Button(text="管理分相册", size_hint_y=None, height=50)
        btn_pwd = Button(text="修改主密码", size_hint_y=None, height=50)
        btn_close = Button(text="关闭", size_hint_y=None, height=50, background_color=(0.7,0.7,0.7,1))
        def open_sub_mgr(x):
            pop.dismiss()
            self.show_sub_vault_manager()
        def open_chg_pwd(x):
            pop.dismiss()
            self.dialog_change_master_password()
        def close_pop(x):
            pop.dismiss()
        btn_sub.bind(on_press=open_sub_mgr)
        btn_pwd.bind(on_press=open_chg_pwd)
        btn_close.bind(on_press=close_pop)
        box.add_widget(btn_sub)
        box.add_widget(btn_pwd)
        box.add_widget(btn_close)
        pop.open()

    # ========== 修改主密码 ==========
    def dialog_change_master_password(self):
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        box.add_widget(Label(text="修改主密码（必须纯数字）", font_size=15))
        ti_old = TextInput(hint_text="输入旧主密码", password=True, size_hint_y=None, height=44)
        ti_new1 = TextInput(hint_text="输入新密码", password=True, size_hint_y=None, height=44)
        ti_new2 = TextInput(hint_text="再次输入新密码", password=True, size_hint_y=None, height=44)
        box.add_widget(ti_old)
        box.add_widget(ti_new1)
        box.add_widget(ti_new2)
        pop = Popup(title="修改主密码", content=box, size_hint=(0.85,0.55))
        btn_bar = BoxLayout(spacing=8, size_hint_y=None, height=48)
        def confirm(x):
            old = ti_old.text.strip()
            n1 = ti_new1.text.strip()
            n2 = ti_new2.text.strip()
            pop.dismiss()
            if self.db.verify_main_password(old) is None:
                self.popup_msg("错误","旧密码不正确")
                return
            if not n1 or not n1.isdigit():
                self.popup_msg("错误","新密码必须是纯数字")
                return
            if n1 != n2:
                self.popup_msg("错误","两次新密码输入不一致")
                return
            try:
                old_row = self.db.get_main_vault_row()
                old_salt = base64.b64decode(old_row["salt"])
                old_k1 = pbkdf2(old, old_salt)
                mk = unwrap_master_key(old_k1)
                new_salt = self.db.update_main_password(n1)
                new_k1 = pbkdf2(n1, new_salt)
                wrap_master_key(mk, new_k1)
                self.master_key = mk
                self.popup_msg("成功","主密码修改完成！")
            except Exception as e:
                self.popup_msg("失败",f"异常：{str(e)}")
        def cancel(x):
            pop.dismiss()
        btn_ok = Button(text="确认")
        btn_cancel = Button(text="取消",background_color=(0.7,0.7,0.7,1))
        btn_ok.bind(on_press=confirm)
        btn_cancel.bind(on_press=cancel)
        btn_bar.add_widget(btn_cancel)
        btn_bar.add_widget(btn_ok)
        box.add_widget(btn_bar)
        pop.open()

    # ========== 分相册管理 ==========
    def show_sub_vault_manager(self):
        outer = BoxLayout(orientation="vertical", padding=10, spacing=8)
        outer.add_widget(Label(text="管理分相册", font_size=18, size_hint_y=None, height=40))
        outer.add_widget(Label(text="分相册使用「金额数字」作为进入密码", font_size=12, size_hint_y=None, height=30))
        scroll = ScrollView()
        self.sub_list_layout = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
        self.sub_list_layout.bind(minimum_height=self.sub_list_layout.setter("height"))
        scroll.add_widget(self.sub_list_layout)
        outer.add_widget(scroll)
        bottom_bar = BoxLayout(spacing=10, size_hint_y=None, height=50)
        btn_add = Button(text="+新增分相册", background_color=(1,0.3,0.3,1))
        btn_close = Button(text="关闭", background_color=(0.7,0.7,0.7,1))
        bottom_bar.add_widget(btn_add)
        bottom_bar.add_widget(btn_close)
        outer.add_widget(bottom_bar)
        pop = Popup(title="分相册管理", content=outer, size_hint=(0.92,0.85))

        def refresh_sub_list():
            self.sub_list_layout.clear_widgets()
            subs = self.db.get_all_sub_vaults()
            if not subs:
                self.sub_list_layout.add_widget(Label(text="暂无分相册", font_size=14, size_hint_y=None, height=60))
                return
            for v in subs:
                card = BoxLayout(orientation="vertical", padding=8, spacing=4, size_hint_y=None, height=140)
                card.add_widget(Label(text=f"相册名：{v['name']}", font_size=14, size_hint_y=None, height=30))
                card.add_widget(Label(text="密码：已加密存储", font_size=11, size_hint_y=None, height=24))
                op_bar = BoxLayout(spacing=4, size_hint_y=None, height=44)
                b_edit_amount = Button(text="改金额", font_size=11)
                b_rename = Button(text="改名", font_size=11)
                b_del = Button(text="删除", font_size=11, background_color=(0.9,0.1,0.1,1))
                def cb_edit_amt(vid=v["id"],vname=v["name"]):
                    pop.dismiss()
                    self.dialog_edit_sub_amount(vid, vname, lambda: (self.show_sub_vault_manager(),))
                def cb_rename(vid=v["id"],vname=v["name"]):
                    pop.dismiss()
                    self.dialog_edit_sub_name(vid, vname, lambda: (self.show_sub_vault_manager(),))
                def cb_del(vid=v["id"],vname=v["name"]):
                    pop.dismiss()
                    self.dialog_delete_sub_vault(vid, vname, lambda: (self.show_sub_vault_manager(),))
                b_edit_amount.bind(on_press=lambda x,vid=v["id"],vname=v["name"]:cb_edit_amt(vid,vname))
                b_rename.bind(on_press=lambda x,vid=v["id"],vname=v["name"]:cb_rename(vid,vname))
                b_del.bind(on_press=lambda x,vid=v["id"],vname=v["name"]:cb_del(vid,vname))
                op_bar.add_widget(b_edit_amount)
                op_bar.add_widget(b_rename)
                op_bar.add_widget(b_del)
                card.add_widget(op_bar)
                self.sub_list_layout.add_widget(card)

        def on_add(x):
            pop.dismiss()
            self.dialog_add_sub_vault(callback=lambda:self.show_sub_vault_manager())
        def on_close(x):
            pop.dismiss()
        btn_add.bind(on_press=on_add)
        btn_close.bind(on_press=on_close)
        refresh_sub_list()
        pop.open()

    def dialog_add_sub_vault(self, callback):
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        ti_name = TextInput(hint_text="分相册名称", size_hint_y=None, height=44)
        ti_amt = TextInput(hint_text="进入金额(纯数字)", size_hint_y=None, height=44)
        box.add_widget(ti_name)
        box.add_widget(ti_amt)
        pop = Popup(title="新增分相册", content=box, size_hint=(0.85,0.45))
        btn_bar = BoxLayout(spacing=8, size_hint_y=None, height=48)
        def ok(x):
            name = ti_name.text.strip()
            amt = ti_amt.text.strip()
            pop.dismiss()
            if not name:
                self.popup_msg("错误","相册名称不能为空")
                callback()
                return
            if not amt.isdigit():
                self.popup_msg("错误","金额必须是纯数字")
                callback()
                return
            vid,err = self.db.create_sub_vault_custom(name, amt)
            if err:
                self.popup_msg("错误",err,callback=callback)
                return
            self.popup_msg("成功",f"已创建「{name}」，密码：{amt}",callback=callback)
        def cancel(x):
            pop.dismiss()
            callback()
        btn_ok = Button(text="确定")
        btn_cancel = Button(text="取消",background_color=(0.7,0.7,0.7,1))
        btn_ok.bind(on_press=ok)
        btn_cancel.bind(on_press=cancel)
        btn_bar.add_widget(btn_cancel)
        btn_bar.add_widget(btn_ok)
        box.add_widget(btn_bar)
        pop.open()

    def dialog_edit_sub_amount(self, vault_id, old_name, callback):
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        box.add_widget(Label(text=f"修改[{old_name}]的进入金额",font_size=14))
        ti = TextInput(hint_text="新纯数字金额", size_hint_y=None, height=44)
        box.add_widget(ti)
        pop = Popup(title="修改金额密码", content=box, size_hint=(0.85,0.4))
        btn_bar = BoxLayout(spacing=8, size_hint_y=None, height=48)
        def ok(x):
            new_amt = ti.text.strip()
            pop.dismiss()
            if not new_amt.isdigit():
                self.popup_msg("错误","金额必须纯数字",callback=callback)
                return
            ok_flag,err = self.db.update_sub_vault_amount(vault_id, new_amt)
            if not ok_flag:
                self.popup_msg("错误",err,callback=callback)
                return
            self.popup_msg("成功",f"新密码：{new_amt}",callback=callback)
        def cancel(x):
            pop.dismiss()
            callback()
        btn_ok = Button(text="确定")
        btn_cancel = Button(text="取消",background_color=(0.7,0.7,0.7,1))
        btn_ok.bind(on_press=ok)
        btn_cancel.bind(on_press=cancel)
        btn_bar.add_widget(btn_cancel)
        btn_bar.add_widget(btn_ok)
        box.add_widget(btn_bar)
        pop.open()

    def dialog_edit_sub_name(self, vault_id, old_name, callback):
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        ti = TextInput(text=old_name, hint_text="相册新名称", size_hint_y=None, height=44)
        box.add_widget(ti)
        pop = Popup(title="重命名分相册", content=box, size_hint=(0.85,0.35))
        btn_bar = BoxLayout(spacing=8, size_hint_y=None, height=48)
        def ok(x):
            new_name = ti.text.strip()
            pop.dismiss()
            if not new_name:
                self.popup_msg("错误","名称不能为空",callback=callback)
                return
            self.db.update_sub_vault_name(vault_id, new_name)
            self.popup_msg("成功",f"已改名为：{new_name}",callback=callback)
        def cancel(x):
            pop.dismiss()
            callback()
        btn_ok = Button(text="确定")
        btn_cancel = Button(text="取消",background_color=(0.7,0.7,0.7,1))
        btn_ok.bind(on_press=ok)
        btn_cancel.bind(on_press=cancel)
        btn_bar.add_widget(btn_cancel)
        btn_bar.add_widget(btn_ok)
        box.add_widget(btn_bar)
        pop.open()

    def dialog_delete_sub_vault(self, vault_id, name, callback):
        def do_delete():
            self.db.delete_sub_vault(vault_id)
            self.popup_msg("已删除",f"分相册「{name}」全部数据已清除",callback=callback)
        box = BoxLayout(orientation="vertical", padding=12, spacing=10)
        box.add_widget(Label(text=f"确定永久删除「{name}」?\n相册内所有图片、文件夹全部不可恢复！", font_size=13))
        pop = Popup(title="危险确认", content=box, size_hint=(0.85,0.4))
        btn_bar = BoxLayout(spacing=10, size_hint_y=None, height=48)
        btn_del = Button(text="确认删除", background_color=(0.9,0.1,0.1,1))
        btn_cancel = Button(text="取消", background_color=(0.7,0.7,0.7,1))
        def cb_del(x):
            pop.dismiss()
            do_delete()
        def cb_cancel(x):
            pop.dismiss()
            callback()
        btn_del.bind(on_press=cb_del)
        btn_cancel.bind(on_press=cb_cancel)
        btn_bar.add_widget(btn_cancel)
        btn_bar.add_widget(btn_del)
        box.add_widget(btn_bar)
        pop.open()

    def on_stop(self):
        self.db.close()

if __name__ == "__main__":
    LightCalcMobileApp().run()
