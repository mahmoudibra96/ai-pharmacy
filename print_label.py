from PIL import Image, ImageDraw, ImageFont
import barcode
from barcode.writer import ImageWriter
import os
import math

# إعدادات
label_width_mm = 40
label_height_mm = 25
dpi = 203
printer_path = "/dev/usb/lp3"

mm_to_inch = 25.4
width_px = int(label_width_mm / mm_to_inch * dpi)
height_px = int(label_height_mm / mm_to_inch * dpi)

# البيانات
lines = [
    "صيدلية الإسراء",
    "بانادول إكسترا",
    "السعر: 15 جنيه"
]
barcode_value = "6223005678123"  # مثال

# تحميل الخط
font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
font_size = 28
font = ImageFont.truetype(font_path, font_size)

# حساب ارتفاع النص
line_spacing = 5
line_heights = [font.getsize(line)[1] for line in lines]
total_text_height = sum(line_heights) + line_spacing * (len(lines) - 1)

# إعداد صورة الأساس
image = Image.new("1", (width_px, height_px), 1)
draw = ImageDraw.Draw(image)

# توسيط النص عموديًا
current_y = (height_px - total_text_height - 60) // 2  # خصم مساحة للباركود

for line in lines:
    text_width, text_height = draw.textsize(line, font=font)
    x = (width_px - text_width) // 2
    draw.text((x, current_y), line, font=font, fill=0, direction="rtl")
    current_y += text_height + line_spacing

# إنشاء الباركود
code128 = barcode.get("code128", barcode_value, writer=ImageWriter())
barcode_path = "/tmp/barcode"  # بدون الامتداد

code128.save(barcode_path, options={"module_height": 10.0, "font_size": 10, "text_distance": 1, "quiet_zone": 1})
barcode_path += ".png"  # الملف النهائي

# تحقق من وجود ملف الباركود
if not os.path.exists(barcode_path):
    raise FileNotFoundError(f"Barcode file not found: {barcode_path}")

# فتح الباركود وتحويله لأبيض وأسود
barcode_img = Image.open(barcode_path).convert("L").resize((width_px, 50))
barcode_img = barcode_img.point(lambda x: 0 if x < 128 else 255, '1')
image.paste(barcode_img, (0, height_px - 50))

# حفظ مؤقت
bmp_path = "/tmp/label_clean.bmp"
image.save(bmp_path)

# تحويل الصورة لبايتات
bytes_per_row = math.ceil(width_px / 8)
bitmap_data = bytearray()
pixels = image.load()
for y in range(height_px):
    byte = 0
    count = 0
    for x in range(width_px):
        byte = (byte << 1) | (0 if pixels[x, y] == 0 else 1)
        count += 1
        if count == 8:
            bitmap_data.append(byte)
            byte = 0
            count = 0
    if count > 0:
        byte = byte << (8 - count)
        bitmap_data.append(byte)

# أمر TSPL
header = f"""SIZE {label_width_mm} mm,{label_height_mm} mm
GAP 2 mm,0
DENSITY 8
CLS
BITMAP 0,0,{bytes_per_row},{height_px},1,
"""

# طباعة
with open(printer_path, "wb") as printer:
    printer.write(header.encode('ascii'))
    printer.write(bitmap_data)
    printer.write(b"\nPRINT 1\n")

print("✅ تمت الطباعة بنجاح مع الباركود وتوسيط النص.")

