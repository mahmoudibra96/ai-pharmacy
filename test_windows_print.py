import win32print
import win32con
import tempfile
import os

def test_windows_print():
    """Test Windows printing functionality"""
    print("Testing Windows printer access...")
    
    # List all available printers
    print("\nAvailable printers:")
    for printer in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL):
        print(f"- {printer[2]}")
    
    # Get default printer
    default_printer = win32print.GetDefaultPrinter()
    print(f"\nDefault printer: {default_printer}")
    
    # Create test data
    test_data = """
SIZE 40 mm,25 mm
GAP 2 mm,0
DENSITY 8
DIRECTION 0
REFERENCE 0,0
CLS
TEXT 10,10,"3",0,1,1,"TEST PRINT"
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
        
        printer_handle = win32print.OpenPrinter(default_printer)
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

if __name__ == "__main__":
    test_windows_print()
