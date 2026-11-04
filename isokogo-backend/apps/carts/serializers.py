from rest_framework import serializers

from .models import Cart, CartItem

class CartItemSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = CartItem
        fields = [
            "id",
            "cart",
            "variant",
            "quantity",
            "added_at",
            "updated_at",
            
        ]
        
        read_only_fields = [
            "id",
            "added_at",
            "updated_at"
        ]
        
    def validate_cart(self, cart):
        request = self.context.get("request")
        
        if request and cart.customer_id != request.user.id:
            raise serializers.ValidationError(
                "You cannot add items to another customer's cart."
            )
        if cart.status != Cart.status.ACTIVE:
            raise serializers.ValidationError(
                "You can only add items to an active cart."
            )
        return cart
    
class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    
    total_items = serializers.SerializerMethodField()
    
    class Meta:
        model = Cart
        fields = [
            "id",
            "customer",
            "status",
            "items",
            "total_items",
            "created_at",
            "updated_at",
        ]
        
        read_only_fields = [
            "id",
            "customer",
            "status",
            "items",
            "total_items",
            "created_at",
            "updated_at",
        ]
        
    def get_total_items(self, obj):
        return sum(
            item.quantity for item in obj.items.all()
        )