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

    def get_windows_printer_path(self):
        """Get printer path for Windows"""
        import platform
        if platform.system() == 'Windows':
            # Try COM ports first (USB to Serial)
            for i in range(1, 10):
                port = f'COM{i}'
                try:
                    import serial
                    ser = serial.Serial(port)
                    ser.close()
                    return port
                except:
                    continue
            
            # Try direct USB printer ports
            alternative_paths = [
                'USB001', 'USB002', 'LPT1', 
                r'\\.\COM1', r'\\.\COM2', r'\\.\COM3'
            ]
            for path in alternative_paths:
                try:
                    with open(path, 'wb') as _:
                        return path
                except:
                    continue
            return 'LPT1'  # Default Windows printer port
        return '/dev/usb/lp0'  # Default Linux printer port

    def print_windows(self, printer_name, data):
        """Print using Windows printer"""
        try:
            import win32print
            import tempfile
            
            # Save data to temporary file
            temp = tempfile.NamedTemporaryFile(delete=False, suffix='.prn')
            temp.write(data)
            temp.close()
            
            try:
                # Try using default printer if no name provided
                if not printer_name:
                    printer_name = win32print.GetDefaultPrinter()
                
                # Open printer
                handle = win32print.OpenPrinter(printer_name)
                try:
                    # Start print job
                    job = win32print.StartDocPrinter(handle, 1, ("Label", None, "RAW"))
                    try:
                        win32print.StartPagePrinter(handle)
                        # Write data to printer
                        with open(temp.name, 'rb') as f:
                            data = f.read()
                            win32print.WritePrinter(handle, data)
                        win32print.EndPagePrinter(handle)
                    finally:
                        win32print.EndDocPrinter(handle)
                finally:
                    win32print.ClosePrinter(handle)
                return True
            finally:
                os.unlink(temp.name)  # Remove temporary file
                
        except ImportError:
            # Fallback to direct port writing if win32print is not available
            try:
                with open(printer_name, 'wb') as p:
                    p.write(data)
                return True
            except:
                return False
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Windows print error: {str(e)}'))
            return False

    def handle(self, *args, **options):
        try:
            # Get appropriate printer path based on OS
            import platform
            is_windows = platform.system() == 'Windows'
            
            # For Windows, we'll handle the port differently
            if is_windows:
                try:
                    import win32print
                    printers = win32print.EnumPrinters(2)
                    if printers:
                        # Try to find a thermal printer
                        thermal_keywords = ['thermal', 'receipt', '80mm', 'pos']
                        for printer in printers:
                            for keyword in thermal_keywords:
                                if keyword.lower() in printer[2].lower():
                                    printer_path = printer[2]
                                    break
                except ImportError:
                    # If win32print is not available, we'll use direct port access
                    pass

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

            # Print based on OS
            if is_windows:
                success = self.print_windows(printer_path, b''.join([
                    header.encode('ascii'),
                    barcode_command.encode('ascii'),
                    bitmap_command.encode('ascii'),
                    bitmap_data,
                    b"\nPRINT 1\n"
                ]))
                if not success:
                    self.stderr.write(self.style.ERROR('Failed to print on Windows'))
                    return
            else:
                # Existing Linux printing code
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
