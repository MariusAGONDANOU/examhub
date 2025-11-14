from .models import Cart, Notification

def cart_context(request):
    """
    Ajoute cart_count au contexte global.
    """
    count = 0
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user)
            count = cart.items.count()
        except Cart.DoesNotExist:
            count = 0
    return {'cart_count': count}

def notifications_context(request):
    """
    Ajoute notifications_count au contexte global.
    """
    count = 0
    if request.user.is_authenticated:
        count = Notification.objects.filter(user=request.user, read=False).count()
    return {'notifications_count': count}