from django.db import models

class Category(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(null=True, blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories')
    image = models.ImageField(upload_to='category_images/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'categories'
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'

class Brand(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    logo = models.ImageField(upload_to='brand_logos/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'brands'
        verbose_name = 'Brand'
        verbose_name_plural = 'Brands'
        
class Product(models.Model):
    id = models.CharField(max_length=36, primary_key=True)  # UUID as string
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    sku = models.CharField(max_length=100, unique=True)
    barcode = models.CharField(max_length=100, unique=True, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='products', null=True, blank=True)
    vendor = models.ForeignKey('vendors.Vendor', on_delete=models.CASCADE, related_name='products')
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=50, null=True, blank=True)
    weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_perishable = models.BooleanField(default=False)
    shelf_life_days = models.IntegerField(null=True, blank=True)
    requires_refrigeration = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta: 
        db_table = 'products'
        verbose_name = 'Products'
        verbose_name_plural = 'Products' 
        
class ProductVariant(models.Model):
    id = models.CharField(max_length=128, primary_key=True)
    product = models.ForeignKey()
    name = models.CharField()
    sku = models.CharField()
    barcode = models.CharField()
    size_value = models.DecimalField()
    size_unit = models.CharField()
    selling_price = models.DecimalField()
    cost_price = models.DecimalField()
    is_active = models.BooleanField(default=True)
    
    class Meta: 
            db_table = 'productVariant'
            verbose_name = 'ProductVariant'
            verbose_name_plural = 'ProductVariant' 

class ProductImage(models.Model):
    id = models.CharField(max_length=36, primary_key=True)  # UUID as string
    product = models.ForeignKey()
    image = models.ImageField()
    alt_text = models.CharField()
    is_primary = models.BooleanField(default=True)
    display_order = models.models.PositiveIntegerField(("max-length=128"))
    
    class Meta: 
                db_table = 'ProductImage'
                verbose_name = 'ProductImage'
                verbose_name_plural = 'ProductImage' 

class ProductAttribute(models.Model):
    id = models.CharField()
    name = models.CharField()
    description = models.TextField()
    
    class Meta: 
                    db_table = 'productAttribute'
                    verbose_name = 'ProductAttribute'
                    verbose_name_plural = 'ProductAttribute' 

class ProductAttributeValue(models.Model):
    id = models.CharField()
    product = models.ForeignKey()
    attribute = models.ForeignKey()
    value = models.ForeignKey()
    
    class Meta:
        db_table = 'productAttributevalue'
        verbose_name = 'ProductAttributeValue'
        verbose_name_plural = 'ProductAttributeValue'

    