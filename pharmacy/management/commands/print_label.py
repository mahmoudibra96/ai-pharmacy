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
        parser.add_argument('--verbose', action='store_true', help='Enable verbose output')

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
            
            # Create temporary file for print data
            temp = tempfile.NamedTemporaryFile(delete=False, suffix='.prn')
            temp.write(data)
            temp_path = temp.name
            temp.close()
            
            try:
                # Use default printer if none specified
                if not printer_name:
                    printer_name = win32print.GetDefaultPrinter()
                
                # Open printer
                printer_handle = win32print.OpenPrinter(printer_name)
                try:
                    if self.verbose:
                        self.stdout.write(self.style.SUCCESS(f'Successfully opened printer: {printer_name}'))
                    
                    # Start print job
                    job = win32print.StartDocPrinter(printer_handle, 1, ("Label", temp_path, "RAW"))
                    
                    try:
                        # Start page
                        win32print.StartPagePrinter(printer_handle)
                        
                        # Write data
                        with open(temp_path, 'rb') as f:
                            data = f.read()
                            win32print.WritePrinter(printer_handle, data)
                        
                        # End page
                        win32print.EndPagePrinter(printer_handle)
                        if self.verbose:
                            self.stdout.write(self.style.SUCCESS('Print job sent successfully'))
                        
                    finally:
                        win32print.EndDocPrinter(printer_handle)
                finally:
                    win32print.ClosePrinter(printer_handle)
                
                return True
                
            except Exception as e:
                if self.verbose:
                    self.stderr.write(self.style.ERROR(f'Windows print error: {str(e)}'))
                return False
                
            finally:
                # Clean up temp file
                os.unlink(temp_path)
                
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

    def convert_to_bitmap(self, image, width_px, height_px):
        """Convert image to bitmap data for printer"""
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
        return bitmap_data

    def get_windows_printer(self, printer_name=None):
        """Get appropriate Windows printer"""
        import win32print
        
        if printer_name:
            return printer_name
            
        # First try to find thermal/receipt printer
        thermal_keywords = ['thermal', 'receipt', '80mm', 'pos', 'label']
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
        
        if self.verbose:
            self.stdout.write(self.style.SUCCESS(f'Available printers: {[p[2] for p in printers]}'))
        
        # Look for thermal printer in available printers
        for printer in printers:
            printer_name = printer[2].lower()
            for keyword in thermal_keywords:
                if keyword in printer_name:
                    if self.verbose:
                        self.stdout.write(self.style.SUCCESS(f'Found thermal printer: {printer[2]}'))
                    return printer[2]
        
        # If no thermal printer found, use default printer
        default_printer = win32print.GetDefaultPrinter()
        if self.verbose:
            self.stdout.write(self.style.SUCCESS(f'Using default printer: {default_printer}'))
        return default_printer

    def handle(self, *args, **options):
        try:
            verbose = options.get('verbose', False)
            if verbose:
                self.stdout.write(self.style.SUCCESS('Starting print job...'))
                self.stdout.write(self.style.SUCCESS(f'Options: {options}'))

            # Get appropriate printer path based on OS
            import platform
            is_windows = platform.system() == 'Windows'
            
            if verbose:
                self.stdout.write(self.style.SUCCESS(f'Operating System: {"Windows" if is_windows else "Linux"}'))
            
            # For Windows, we'll handle the port differently
            if is_windows:
                try:
                    import win32print
                    if verbose:
                        self.stdout.write(self.style.SUCCESS('Enumerating Windows printers...'))
                    printers = win32print.EnumPrinters(2)
                    if printers and verbose:
                        self.stdout.write(self.style.SUCCESS(f'Available printers: {[p[2] for p in printers]}'))
                except ImportError:
                    # If win32print is not available, we'll use direct port access
                    pass

            # Get medicine
            try:
                medicine = Medicine.objects.get(barcode_number=options['barcode'])
                if verbose:
                    self.stdout.write(self.style.SUCCESS(f'Found medicine: {medicine.name}'))
            except Medicine.DoesNotExist:
                self.stderr.write(self.style.ERROR('Medicine not found'))
                return

            # Generate label image
            if verbose:
                self.stdout.write(self.style.SUCCESS('Generating label image...'))
            image, width_px, height_px = self.generate_label_image(medicine)

            # Calculate bitmap data
            if verbose:
                self.stdout.write(self.style.SUCCESS('Converting image to bitmap data...'))
            bytes_per_row = math.ceil(width_px / 8)
            bitmap_data = self.convert_to_bitmap(image, width_px, height_px)

            if verbose:
                self.stdout.write(self.style.SUCCESS('Preparing printer commands...'))
                self.stdout.write(self.style.SUCCESS(f'Image dimensions: {width_px}x{height_px} pixels'))
                self.stdout.write(self.style.SUCCESS(f'Bytes per row: {bytes_per_row}'))

            header = f"""SIZE 40 mm,25 mm
GAP 2 mm,0
DENSITY 8
DIRECTION 0
REFERENCE 0,0
CLS
"""
            barcode_command = f"""BARCODE 10,{int(height_px*0.6)},"128",{int(height_px*0.3)},1,0,2,2,"{medicine.barcode_number}"
"""
            bitmap_command = f"""BITMAP 0,0,{bytes_per_row},{height_px},1,
"""

            printer_path = options['printer']
            copies = options['copies']

            if verbose:
                self.stdout.write(self.style.SUCCESS(f'Printer path: {printer_path}'))
                self.stdout.write(self.style.SUCCESS(f'Number of copies: {copies}'))

            # Print based on OS
            if is_windows:
                if verbose:
                    self.stdout.write(self.style.SUCCESS('Using Windows printing method...'))
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
                if verbose:
                    self.stdout.write(self.style.SUCCESS('Using Linux printing method...'))
                with open(printer_path, "wb") as printer:
                    for copy in range(copies):
                        if verbose:
                            self.stdout.write(self.style.SUCCESS(f'Printing copy {copy + 1} of {copies}...'))
                        printer.write(header.encode('ascii'))
                        printer.write(barcode_command.encode('ascii'))
                        printer.write(bitmap_command.encode('ascii'))
                        printer.write(bitmap_data)
                        printer.write(b"\nPRINT 1\n")

            self.stdout.write(self.style.SUCCESS('✅ تمت الطباعة بنجاح'))
            
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
            if verbose:
                import traceback
                self.stderr.write(self.style.ERROR(traceback.format_exc()))
