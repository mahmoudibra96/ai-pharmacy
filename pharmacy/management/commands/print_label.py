from django.core.management.base import BaseCommand
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont
import os
import math
from pharmacy.models import Medicine

class Command(BaseCommand):
    help = 'Print a label for a medicine using a thermal printer'

    def add_arguments(self, parser):
        parser.add_argument('barcode', type=str, help='Barcode number of the medicine')
        parser.add_argument('--printer', type=str, 
                          default=settings.PRINTER_SETTINGS['PRINTER_PATH'],
                          help='Printer device path')
        parser.add_argument('--copies', type=int, default=1, help='Number of copies to print')

    def generate_label_image(self, medicine):
        # إعدادات من ملف الإعدادات
        label_width_mm = settings.PRINTER_SETTINGS['LABEL_WIDTH']
        label_height_mm = settings.PRINTER_SETTINGS['LABEL_HEIGHT']
        dpi = settings.PRINTER_SETTINGS['PRINTER_DPI']
        
        # تحويل الحجم من mm إلى pixel
        mm_to_inch = 25.4
        width_px = int(label_width_mm / mm_to_inch * dpi)
        height_px = int(label_height_mm / mm_to_inch * dpi)

        # إعداد الصورة
        image = Image.new("1", (width_px, height_px), 1)  # "1" = أبيض وأسود
        draw = ImageDraw.Draw(image)

        # تحميل خط يدعم العربي - بحجم أصغر
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        font = ImageFont.truetype(font_path, 22)

        # البيانات
        lines = [
            "صيدلية الإسراء",
            medicine.name[:20],  # تحديد طول الاسم
            f"السعر: {medicine.price} ج.م"
        ]

        # توزيع النص بشكل أفضل - نأخذ فقط النصف العلوي من الملصق
        text_height = height_px * 0.5  # ترك مساحة للباركود
        line_height = text_height / len(lines)
        y = 5  # بداية من الأعلى بهامش صغير

        for i, line in enumerate(lines):
            try:
                text_bbox = draw.textbbox((0, 0), line, font=font)
                text_width = text_bbox[2] - text_bbox[0]
            except AttributeError:
                text_width, _ = draw.textsize(line, font=font)
            
            x = (width_px - text_width) / 2  # وسط
            draw.text((x, y), line, font=font, fill=0, align="right", direction="rtl")
            y += line_height

        return image, width_px, height_px

    def handle(self, *args, **options):
        try:
            printer_path = options.get('printer') or settings.PRINTER_SETTINGS['PRINTER_PATH']
            
            # Check if printer exists and is accessible
            if not os.path.exists(printer_path):
                alternative_paths = ['/dev/usb/lp0', '/dev/usb/lp1', '/dev/usb/lp2', '/dev/usb/lp3']
                for path in alternative_paths:
                    if os.path.exists(path):
                        printer_path = path
                        break
                else:
                    self.stderr.write(self.style.ERROR(f'Printer not found at {printer_path} or any alternative paths'))
                    return

            # Get medicine
            try:
                medicine = Medicine.objects.get(barcode_number=options['barcode'])
            except Medicine.DoesNotExist:
                self.stderr.write(self.style.ERROR('Medicine not found'))
                return

            # Generate label image
            image, width_px, height_px = self.generate_label_image(medicine)

            # حساب عدد البايتات عرضاً
            bytes_per_row = math.ceil(width_px / 8)

            # قراءة بيانات الصورة بشكل خام
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

            # تجهيز أمر TSPL
            header = f"""SIZE 40 mm,25 mm
GAP 2 mm,0
DENSITY 8
DIRECTION 0
REFERENCE 0,0
CLS
"""
            # أمر الباركود
            barcode_command = f"""BARCODE 10,{int(height_px*0.6)},"128",{int(height_px*0.3)},1,0,2,2,"{medicine.barcode_number}"
"""
            # أمر الـBITMAP
            bitmap_command = f"""BITMAP 0,0,{bytes_per_row},{height_px},1,
"""

            printer_path = options['printer']
            copies = options['copies']

            # إرسال الأمر للطابعة
            with open(printer_path, "wb") as printer:
                for _ in range(copies):
                    printer.write(header.encode('ascii'))
                    printer.write(barcode_command.encode('ascii'))
                    printer.write(bitmap_command.encode('ascii'))
                    printer.write(bitmap_data)
                    printer.write(b"\nPRINT 1\n")

            self.stdout.write(self.style.SUCCESS('✅ تمت الطباعة بنجاح'))
            
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
