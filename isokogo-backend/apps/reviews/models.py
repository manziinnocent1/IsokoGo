from django.db import models

class ProductReview(models.Model):
    id = models.CharField()
    customer = models.ForeignKey()
    product = models.ForeignKey()
    order_item = models.ForeignKey()
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField()
    
    class Meta:
            db_table = 'product review'
            verbose_name = 'Product Review'
            verbose_name_plural = 'Product Review'

