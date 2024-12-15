from django.core.management.base import BaseCommand
from pharmacy.models import Medicine
from django.core.files import File
from django.conf import settings
import random
from decimal import Decimal
import os

class Command(BaseCommand):
    help = 'Adds dummy medicine products to the database'

    def add_arguments(self, parser):
        parser.add_argument('count', type=int, help='Number of dummy products to create')

    def handle(self, *args, **kwargs):
        count = kwargs['count']
        
        # Lists for generating random data
        prefixes = ['Med', 'Pharma', 'Health', 'Care', 'Bio', 'Life', 'Well', 'Cure', 'Heal', 'Vital']
        suffixes = ['Plus', 'Max', 'Ultra', 'Fort', 'Extra', 'Pro', 'Advanced', 'Elite', 'Premium', 'Super']
        forms = ['Tablet', 'Capsule', 'Syrup', 'Injection', 'Cream', 'Gel', 'Spray', 'Drop', 'Powder', 'Ointment']
        strengths = ['250mg', '500mg', '1000mg', '50mg', '100mg', '5mg', '10mg', '20mg', '25mg', '75mg']
        
        categories = [choice[0] for choice in Medicine.CATEGORY_CHOICES]
        
        # Sample descriptions
        descriptions = [
            "Used for treating {condition}. Provides quick relief and long-lasting effects.",
            "Effective treatment for {condition}. Take as directed by healthcare professional.",
            "Helps manage {condition} symptoms. Suitable for adults and children over 12.",
            "Professional strength formula for {condition}. Fast-acting relief.",
            "Advanced treatment for {condition}. Clinically proven effectiveness."
        ]
        
        conditions = [
            "pain and inflammation",
            "allergies",
            "digestive issues",
            "respiratory problems",
            "skin conditions",
            "headaches",
            "muscle pain",
            "joint pain",
            "fever",
            "cold and flu symptoms"
        ]

        created_count = 0
        
        self.stdout.write("Starting to create dummy products...")
        
        for i in range(count):
            try:
                # Generate random product name
                name = f"{random.choice(prefixes)}{random.choice(suffixes)} {random.choice(forms)} {random.choice(strengths)}"
                
                # Generate random barcode (12 digits)
                barcode = ''.join([str(random.randint(0, 9)) for _ in range(12)])
                
                # Generate random description
                desc_template = random.choice(descriptions)
                description = desc_template.format(condition=random.choice(conditions))
                
                # Create medicine object
                medicine = Medicine.objects.create(
                    name=name,
                    description=description,
                    price=Decimal(random.uniform(5.99, 199.99)).quantize(Decimal('0.01')),
                    stock=random.randint(0, 100),
                    category=random.choice(categories),
                    barcode_number=barcode,
                    is_active=True,
                    reorder_level=random.randint(5, 20)
                )
                
                created_count += 1
                
                if created_count % 100 == 0:
                    self.stdout.write(f"Created {created_count} products...")
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error creating product: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS(f'Successfully created {created_count} dummy products')) 