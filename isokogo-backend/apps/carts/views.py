from django.db.models import Prefetch
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from .models import Cart, CartItem
from .serializers import CartSerializer, CartItemSerializer

class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return(
            Cart.objects.filter(customer=self.request.user).prefetch_related("items").order_by("_created_at")
        
        )
        
    def perform_create(self, serializer):
        existing_cart = Cart.objects.filter(
            customer=self.request.user,
            status=Cart.Status.ACTIVE
        ).exists()
        
        if existing_cart:
            raise ValidationError({
                "detail": "you already have an active cart."
            })
            
        serializer.save(customer=self.request.user)
        
    def partial_update(self, request, *args, **kwargs):
        raise ValidationError(
            "cart details cannot be updated directly."
        )
        
class CartItemViewSet(viewsets.ModelViewSet):
    
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return(
            CartItem.objects.filter(cart__customer=self.request.user).select_related("cart", "variant").order_by("-added_at")
        )
        
    def perform_update(self, serializer):
        cart_item = self.get_object()
        
        if cart_item.cart.status != Cart.Status.ACTIVE:
            raise ValidationError(
                " Items can only be updated in an active cart."
            )
            
        serializer.save()
        
    def perform_destroy(self, instance):
        if instance.cart.status != Cart.Status.ACTIVE:
            raise ValidationError(
                "items can only be removed from an active cart."
            )
        instance.delete()
