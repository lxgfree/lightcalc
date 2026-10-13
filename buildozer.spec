[app]

# 应用标题（显示在手机桌面）
title = 轻计算器

# 包名（英文，只能小写字母+数字+下划线）
package.name = lightcalc

# 包域名（反向域名格式，随便填但格式要对）
package.domain = org.lightcalc

# 源代码目录（. 表示当前目录）
source.dir = .

# 入口文件（必须是 main.py，buildozer 约定）
source.include_exts = py,png,jpg,jpeg,ttf,ttc,otf,kv,atlas
source.include_patterns = assets/*,images/*,fonts/*

# 应用版本号
version = 1.0

# 应用要求（Python + Kivy + 你用到的第三方库）
# 注意：sqlite3 在 Python3 标准库里已内置，buildozer 会自动处理；
# pycryptodome 必须写成 pycryptodome（不能写 Crypto）；
# Pillow 在 buildozer 里的 recipe 名就是 pillow。
requirements = python3,kivy==2.3.0,pillow,pycryptodome

# 屏幕方向：竖屏（计算器适合竖屏）
orientation = portrait

# 全屏显示
fullscreen = 0

# 安卓相关
android.api = 33
android.minapi = 24
android.sdk = 24
android.ndk = 25b
android.ndk_api = 21

# 是否允许备份
android.allow_backup = True

# 是否释放模式（debug 先调通，release 再改 1）
android.release_artifact = apk
android.apptheme = @android:style/Theme.NoTitleBar.Fullscreen

# Android 权限（存储读写，Android 13+ 用 READ_MEDIA_IMAGES）
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_IMAGES

# 架构（生成两个架构：arm64-v8a + armeabi-v7a，覆盖主流手机）
android.archs = arm64-v8a, armeabi-v7a

# 入口
entrypoint = main.py

# Kivy 启动加载图（可选，留空使用默认）
#android.presplash_color = #000000
#android.presplash_fadein = 0

# Log 等级（调试用 2，正式打包可改 0）
log_level = 2

# -----------------------------------------------------------------------------
# 高级配置（一般不用改）
# -----------------------------------------------------------------------------

[buildozer]

# 构建日志等级（2 = 详细，方便排错）
log_level = 2

# 构建时 warn_on_root，避免 root 权限导致奇怪问题
warn_on_root = 1

# 构建输出目录
bin_dir = bin

# 构建临时目录
build_dir = .buildozer
