import win32print
import win32con
import tempfile
import os

def get_thermal_printer():
    """Try to find a thermal printer"""
    thermal_keywords = ['thermal', 'receipt', '80mm', 'pos', 'label']
    printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
    
    for printer in printers:
        printer_name = printer[2].lower()
        for keyword in thermal_keywords:
            if keyword in printer_name:
                return printer[2]
    return None

def test_windows_print(printer_name=None):
    """Test Windows printing functionality"""
    print("Testing Windows printer access...")
    
    # List all available printers
    printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
    print("\nAvailable printers:")
    for printer in printers:
        name, status = printer[2], printer[18] if len(printer) > 18 else "Unknown"
        print(f"- {name} (Status: {status})")
    
    # Get printer to use
    if not printer_name:
        # Try to find thermal printer first
        printer_name = get_thermal_printer()
        if printer_name:
            print(f"\nFound thermal printer: {printer_name}")
        else:
            # Fall back to default printer
            printer_name = win32print.GetDefaultPrinter()
            print(f"\nNo thermal printer found, using default printer: {printer_name}")
    else:
        # Verify the specified printer exists
        printer_exists = any(p[2] == printer_name for p in printers)
        if not printer_exists:
            print(f"\nWarning: Specified printer '{printer_name}' not found!")
            return False
        print(f"\nUsing specified printer: {printer_name}")
    
    # Create test data with Arabic support
    test_data = """SIZE 40 mm,25 mm
GAP 2 mm,0
DENSITY 8
CODEPAGE UTF-8
DIRECTION 0
REFERENCE 0,0
CLS
TEXT 10,10,"3",0,1,1,"اختبار الطباعة"
TEXT 10,30,"3",0,1,1,"TEST PRINT"
TEXT 10,50,"2",0,1,1,"طابعة حرارية"
BARCODE 10,80,"128",50,1,0,2,2,"123456789"
PRINT 1
"""
    
    # Create temporary file
    temp = tempfile.NamedTemporaryFile(delete=False, suffix='.prn')
    temp.write(test_data.encode('ascii'))
    temp_path = temp.name
    temp.close()
    
    try:
        # Try to print
        print("\nTrying to print test data...")
        
        printer_handle = win32print.OpenPrinter(printer_name)
        try:
            print("Printer opened successfully")
            
            # Start print job
            print("Starting print job...")
            job = win32print.StartDocPrinter(printer_handle, 1, ("Test", temp_path, "RAW"))
            
            try:
                # Start page
                win32print.StartPagePrinter(printer_handle)
                
                # Write data
                with open(temp_path, 'rb') as f:
                    data = f.read()
                    win32print.WritePrinter(printer_handle, data)
                
                # End page
                win32print.EndPagePrinter(printer_handle)
                print("Print job sent successfully")
                
            finally:
                win32print.EndDocPrinter(printer_handle)
        finally:
            win32print.ClosePrinter(printer_handle)
            
        print("\nTest completed successfully")
        return True
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        return False
        
    finally:
        # Clean up temp file
        os.unlink(temp_path)

def parse_args():
    """Parse command line arguments"""
    import argparse
    parser = argparse.ArgumentParser(description='Test Windows printer functionality')
    parser.add_argument('--printer', type=str, help='Printer name to test')
    parser.add_argument('--list', action='store_true', help='List available printers and exit')
    parser.add_argument('--dry-run', action='store_true', help='Test everything but skip actual printing')
    parser.add_argument('--port', type=str, help='Use specific port (e.g., COM1, LPT1)')
    return parser.parse_args()

def list_printers():
    """List all available printers with details"""
    print("\nAvailable Printers:")
    print("-" * 60)
    print(f"{'Printer Name':<30} {'Status':<15} {'Port':<15}")
    print("-" * 60)
    
    for printer in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL):
        name = printer[2]
        try:
            handle = win32print.OpenPrinter(name)
            try:
                info = win32print.GetPrinter(handle, 2)
                status = "Ready" if info['Status'] == 0 else "Error"
                port = info.get('pPortName', 'Unknown')
            finally:
                win32print.ClosePrinter(handle)
        except:
            status = "Error"
            port = "Unknown"
        
        print(f"{name:<30} {status:<15} {port:<15}")
    print("-" * 60)

if __name__ == "__main__":
    import platform
    if platform.system() != 'Windows':
        print("This script must be run on Windows!")
        exit(1)
        
    args = parse_args()
    
    if args.list:
        list_printers()
        exit(0)
        
    # If port is specified, try to use it
    printer_name = args.printer
    if args.port:
        if not args.port.startswith(('COM', 'LPT')):
            print(f"Invalid port format: {args.port}. Should be COM1, LPT1, etc.")
            exit(1)
        printer_name = args.port
    
    # Run the test
    print("=== Windows Printer Test ===")
    print(f"Mode: {'Dry run (no printing)' if args.dry_run else 'Normal'}")
    if args.dry_run:
        print("Checking printer access and configuration...")
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
        for printer in printers:
            name, status = printer[2], "Unknown"
            try:
                handle = win32print.OpenPrinter(name)
                win32print.ClosePrinter(handle)
                status = "OK"
            except:
                status = "Error"
            print(f"Printer '{name}': {status}")
        exit(0)
    
    success = test_windows_print(printer_name)
    exit(0 if success else 1)
