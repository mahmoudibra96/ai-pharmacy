"""
Import products from Excel file, including expiration dates.
"""
from django.core.management.base import BaseCommand
import pandas as pd
from pharmacy.models import Medicine, StockEntry
from django.utils import timezone
from datetime import datetime
import os


class Command(BaseCommand):
    help = 'Import products from Excel file'

    def add_arguments(self, parser):
        parser.add_argument('excel_file', type=str, help='Path to the Excel file')

    def parse_date(self, date_str):
        if pd.isna(date_str):
            return None
        try:
            # Try parsing date in format "d/m/yyyy"
            return datetime.strptime(str(date_str).strip(), '%d/%m/%Y')
        except ValueError:
            try:
                # Try parsing date in format "d/m/yyyy" with no leading zeros
                return datetime.strptime(str(date_str).strip(), '%-d/%-m/%Y')
            except ValueError:
                return None

    def handle(self, *args, **options):
        file_path = options['excel_file']
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return
            
        try:
            # Read Excel file
            self.stdout.write(f'Reading file: {file_path}')
            df = pd.read_excel(file_path)
            
            # Map Excel columns to model fields
            column_mapping = {
                'الباركود': 'barcode',
                'اسم الصنف': 'name',
                'الكمية': 'quantity',
                'سعر الشراء': 'purchase_price',
                'سعر البيع': 'price',
                'تاريخ انتهاء الصلاحيه': 'expiry_date',
                'إجمالي سعر البيع': 'total_sell_price'  # We won't use this in the model
            }
            
            # Check if required columns exist
            missing_columns = [col for col in column_mapping.keys() if col not in df.columns]
            if missing_columns:
                self.stdout.write(
                    self.style.ERROR(
                        f'Missing required columns: {", ".join(missing_columns)}'
                    )
                )
                return
            
            # Rename columns
            df = df.rename(columns=column_mapping)
            
            total_added = 0
            total_updated = 0
            
            for _, row in df.iterrows():
                try:
                    # Skip rows with empty barcode
                    if pd.isna(row['barcode']):
                        continue
                    
                    self.stdout.write(f"Processing row: {row}")
                    barcode = str(int(row['barcode']))  # Convert to string and remove decimals
                    name = str(row['name']).strip()
                    quantity = int(row['quantity'])
                    self.stdout.write(f"Quantity from Excel: {quantity}")
                    purchase_price = float(row['purchase_price'])
                    price = float(row['price'])
                    expiry_date = self.parse_date(row['expiry_date'])
                    self.stdout.write(f"Parsed values: barcode={barcode}, name={name}, quantity={quantity}, price={price}, expiry_date={expiry_date}")
                    
                    if not name:
                        self.stdout.write(self.style.WARNING(f'Skipping row with empty name: {row}'))
                        continue
                        
                    if quantity < 0:
                        self.stdout.write(self.style.WARNING(f'Invalid quantity for {name}: {quantity}'))
                        continue
                        
                    if price < 0 or purchase_price < 0:
                        self.stdout.write(self.style.WARNING(f'Invalid price for {name}: price={price}, purchase_price={purchase_price}'))
                        continue

                    if not expiry_date:
                        self.stdout.write(self.style.WARNING(f'Invalid or missing expiry date for {name}, using default (1 year)'))
                        expiry_date = timezone.now() + timezone.timedelta(days=365)
                    
                    # Try to get existing medicine or create new one
                    medicine, created = Medicine.objects.get_or_create(
                        barcode_number=barcode,
                        defaults={
                            'name': name,
                            'price': price,
                            'purchase_price': purchase_price,
                            'category': 'OTHERS',  # Default category
                            'reorder_level': 5,  # Default reorder level
                        }
                    )
                    
                    if not created:
                        # Update existing medicine
                        medicine.name = name
                        medicine.price = price
                        medicine.purchase_price = purchase_price
                        medicine.save()
                        total_updated += 1
                        self.stdout.write(self.style.SUCCESS(f'Updated existing medicine: {name}'))
                    else:
                        total_added += 1
                        self.stdout.write(self.style.SUCCESS(f'Created new medicine: {name}'))
                    
                    # Add stock entry for the quantity
                    if quantity > 0:
                        # Create new stock entry
                        stock_entry = StockEntry.objects.create(
                            medicine=medicine,
                            quantity=quantity,
                            expiration_date=expiry_date
                        )
                        
                        # Update medicine stock using the new calculation method
                        old_stock = medicine.stock
                        medicine.update_stock()
                        new_stock = medicine.stock
                        
                        action = "Updated" if not created else "Created new"
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'{action} stock entry for {medicine.name}:\n'
                                f'- Quantity added: {quantity}\n'
                                f'- Expiry date: {expiry_date.strftime("%d/%m/%Y")}\n'
                                f'- Previous stock: {old_stock}\n'
                                f'- New total stock: {new_stock}'
                            )
                        )
                        
                except (ValueError, TypeError) as e:
                    self.stdout.write(self.style.WARNING(f'Error processing row: {row}. Error: {str(e)}'))
                    continue
                
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully imported {total_added} new medicines and updated {total_updated} existing ones'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error importing products: {str(e)}')
            )
