from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from .models import Cart, CartItem, Pack, Order, OrderItem, DownloadToken, PurchasedPack, Notification
from django.conf import settings
from decimal import Decimal

import stripe
import requests
import uuid
import json

from .models import Cart, CartItem, Pack, Order, OrderItem

# --- Stripe ---
stripe.api_key = settings.STRIPE_SECRET_KEY


def _get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart

@login_required
@require_POST
def add_to_cart(request):
    """Ajoute un pack au panier en empêchant les doublons.

    - Si le pack est déjà présent dans le panier, on NE modifie pas la quantité
      et on renvoie un message explicite.
    - Réponse JSON pour les requêtes AJAX (utilisé par les boutons « Ajouter au panier »).
    - Messages framework + redirection sinon.
    """
    pack_id = request.POST.get('pack_id')
    if not pack_id:
        return HttpResponseBadRequest("pack_id manquant")

    pack = get_object_or_404(Pack, pk=pack_id, is_active=True)
    cart = _get_or_create_cart(request.user)
    item, created = CartItem.objects.get_or_create(
        cart=cart, pack=pack, defaults={'quantity': 1}
    )

    # Déjà présent -> on n'autorise PAS l'ajout une 2e fois
    if not created:
        msg = (
            f"Le pack {pack} figure déjà dans votre panier. "
            "Il vous est donc impossible de l’ajouter de nouveau car un même pack "
            "ne peut être ajouté deux ou plusieurs fois au panier."
        )
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'ok': False,
                'already_in_cart': True,
                'cart_count': cart.items.count(),
                'pack_name': str(pack),
                'message': msg,
            }, status=200)
        messages.warning(request, msg)
        return redirect(request.META.get("HTTP_REFERER", reverse('exams:index')))

    # Ajout effectué
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'already_in_cart': False,
            'cart_count': cart.items.count(),
            'pack_name': str(pack),
            'item_id': item.id,
        })
    messages.success(request, f"Le pack « {pack} » a été ajouté à votre panier.")
    return redirect('exams:cart_detail')

@login_required
@require_POST
def add_multiple_to_cart(request):
    """Ajoute plusieurs packs d'un coup depuis la modale du panier.
    Attend un champ `pack_ids` (liste) dans POST. Répond en JSON.
    """
    pack_ids = request.POST.getlist('pack_ids[]') or request.POST.getlist('pack_ids')
    if not pack_ids:
        return JsonResponse({'ok': False, 'error': 'Aucun pack sélectionné.'}, status=400)

    cart = _get_or_create_cart(request.user)
    added = 0
    skipped = []
    for pid in pack_ids:
        try:
            pack = Pack.objects.get(pk=pid, is_active=True)
        except Pack.DoesNotExist:
            continue
        obj, created = CartItem.objects.get_or_create(cart=cart, pack=pack, defaults={'quantity': 1})
        if created:
            added += 1
        else:
            skipped.append(str(pack))

    msg = f"{added} pack(s) ajouté(s) au panier."
    if skipped:
        msg += " " + ", ".join([f"{name}" for name in skipped]) + " déjà présent(s) dans votre panier."

    return JsonResponse({
        'ok': True,
        'added': added,
        'skipped': skipped,
        'cart_count': cart.items.count(),
        'message': msg,
    }, status=200)

@login_required
def cart_detail(request):
    cart = _get_or_create_cart(request.user)
    items = cart.items.select_related('pack', 'pack__exam', 'pack__subject')
    total = cart.total_amount
    all_packs = (
        Pack.objects.filter(is_active=True)
        .select_related('exam', 'subject')
        .order_by('exam__name', 'pack_type', 'subject__name')
    )
    # Liste des packs déjà présents
    in_cart_ids = list(items.values_list('pack_id', flat=True))
    ctx = {
        'cart': cart,
        'items': items,
        'total': total,
        'all_packs': all_packs,
        'in_cart_ids': in_cart_ids,
    }
    return render(request, 'cart_detail.html', ctx)
    

@login_required
@require_POST
def remove_from_cart(request, item_id):
    cart = _get_or_create_cart(request.user)
    item = get_object_or_404(CartItem, id=item_id, cart=cart)
    item.delete()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'cart_count': cart.items.count()})
    return redirect('exams:cart_detail')


@login_required
@require_POST
def cart_checkout(request):
    """
    Crée une Order et lance le paiement (Stripe ou CinetPay).
    """
    cart = _get_or_create_cart(request.user)
    items = list(cart.items.select_related('pack'))
    if not items:
        return redirect('exams:cart_detail')

    # 1) Créer Order
    order = Order.objects.create(
        user=request.user,
        status='PENDING',
        total_amount=0,
        payment_method=request.POST.get("payment_method", "MOMO")  # MOMO par défaut
    )

    total = 0
    stripe_line_items = []
    order_items_bulk = []

    for it in items:
        oi = OrderItem(order=order, pack=it.pack, unit_price=it.unit_price, quantity=it.quantity)
        order_items_bulk.append(oi)
        total += it.subtotal

        stripe_line_items.append({
            "price_data": {
                "currency": "xof",
                "product_data": {"name": str(it.pack)},
                "unit_amount": int(it.unit_price),
            },
            "quantity": it.quantity,
        })

    OrderItem.objects.bulk_create(order_items_bulk)
    order.total_amount = total
    order.save(update_fields=['total_amount', 'payment_method'])

    # 2) Paiement STRIPE
    if order.payment_method.upper() == "STRIPE":
        success_url = request.build_absolute_uri(reverse('exams:payment_success')) + "?session_id={CHECKOUT_SESSION_ID}"
        cancel_url = request.build_absolute_uri(reverse('exams:payment_cancel'))

        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=stripe_line_items,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"order_id": str(order.id), "user_id": str(request.user.id)},
        )

        order.stripe_session_id = session.id
        order.save(update_fields=['stripe_session_id'])
        return redirect(session.url, permanent=False)

    # 3) Paiement MOBILE MONEY via CINETPAY
    transaction_id = f"order{order.id}-{uuid.uuid4().hex[:12]}"
    notify_url = request.build_absolute_uri(reverse("exams:momo_webhook"))
    return_url = request.build_absolute_uri(reverse("exams:payment_success"))

    payload = {
        "apikey": settings.CINETPAY_API_KEY,
        "site_id": settings.CINETPAY_SITE_ID,
        "transaction_id": transaction_id,
        "amount": int(total),  # entier
        "currency": "XOF",
        "description": f"Paiement commande #{order.id}",
        "notify_url": notify_url,
        "return_url": return_url,
        "metadata": json.dumps({"order_id": str(order.id)}),
    }

    try:
        response = requests.post(
            "https://api-checkout.cinetpay.com/v2/payment",
            json=payload,
            timeout=15
        )
        response_data = response.json()
    except Exception as e:
        return render(request, "payment_failed.html", {"error": str(e)})

    print("Payload envoyé à CinetPay:", payload)
    print("Réponse CinetPay:", response_data)

    if response_data.get("code") == "201":
        payment_url = response_data["data"]["payment_url"]
        return redirect(payment_url)
    else:
        return render(request, "payment_failed.html", {
            "error": response_data.get("description", "Erreur inconnue"),
            "details": response_data
        })

@login_required
def payment_success(request):
    """
    1) Récupère la dernière commande de l'utilisateur.
    2) Garantit la création des DownloadToken pour chaque item payé.
    3) Crée la notification post-paiement avec la liste des packs.
    4) Envoie à la page de succès les données pour la modale.
    """
    order = (
        Order.objects.filter(user=request.user)
        .order_by('-created_at')
        .first()
    )

    packs_info = []
    total_paid = 0

    if order:
        # Si pour une raison quelconque le statut n'est pas déjà PAID (ex: simulateur),
        # on le force ici après retour succès.
        if order.status != "PAID":
            order.status = "PAID"
            order.save()

        total_paid = int(order.total_amount or 0)

        # Créer/assurer les tokens + PurchasedPack
        for item in order.items.all():
            # Token de téléchargement (si absent)
            tok, _ = DownloadToken.objects.get_or_create(
                item=item,
                defaults={
                    'expires_at': timezone.now() + timedelta(hours=settings.DOWNLOAD_TOKEN_TTL_HOURS),
                    'remaining_downloads': settings.DOWNLOAD_MAX_TIMES,
                }
            )
            # Possession (historique)
            PurchasedPack.objects.get_or_create(user=request.user, pack=item.pack)

            packs_info.append({
                'name': str(item.pack),
                'download_url': reverse('exams:download_file', args=[tok.token]),
            })

        # Créer une notification (message + payload (packs + total))
        notif_message = (
            f"Paiement de la somme de {total_paid} F effectué avec succès. "
            "Pour obtenir les packs que vous venez d’acheter sur votre appareil, "
            "cliquez sur le bouton « Télécharger ZIP » présent sur chacun de ces packs."
        )
        Notification.objects.create(
            user=request.user,
            message=notif_message,
            payload={'total': total_paid, 'packs': packs_info},
        )

    return render(
        request,
        'payment_success.html',
        {
            'show_modal': True,
            'total_paid': total_paid,
            'packs_info': packs_info,
        }
    )


@login_required
def payment_simulator(request):
    """
    Permet de tester SANS payer :
    - Crée une commande à partir du panier courant
    - Marque la commande comme payée
    - Redirige vers la page de succès (qui affichera la modale, créera la notif, etc.)
    """
    cart, _ = Cart.objects.get_or_create(user=request.user)
    items = list(cart.items.all())
    if not items:
        messages.warning(request, "Votre panier est vide : ajoutez d'abord un/des packs pour tester.")
        return redirect('exams:cart_detail')

    order = Order.objects.create(user=request.user, total_amount=sum(i.unit_price for i in items))
    for it in items:
        OrderItem.objects.create(order=order, pack=it.pack, unit_price=it.unit_price, quantity=it.quantity)

    order.status = "PAID"
    order.save()

    # Optionnel : vider le panier après commande
    cart.items.all().delete()

    return redirect('exams:payment_success')

@login_required
def payment_cancel(request):
    """
    Annulation du paiement (Stripe, CinetPay, ou simulateur).
    On affiche juste un message d’erreur et on redirige vers le panier.
    """
    messages.error(request, "Le paiement a été annulé. Vous pouvez réessayer.")
    return redirect('exams:cart_detail')

@csrf_exempt
def stripe_webhook(request):
    """
    Webhook Stripe simulé.
    Pour l’instant, on ne traite rien car le paiement réel n’est pas testé.
    On renvoie juste 200 OK pour que Django ait la vue.
    """
    return HttpResponse(status=200)

@csrf_exempt
def momo_webhook(request):
    """
    Webhook CinetPay → met à jour la commande.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            print("Webhook MoMo reçu:", data)

            order_id = None
            if "metadata" in data:
                try:
                    metadata = json.loads(data.get("metadata"))
                    order_id = metadata.get("order_id")
                except Exception:
                    pass

            if not order_id:
                return JsonResponse({"error": "order_id manquant"}, status=400)

            try:
                order = Order.objects.get(pk=order_id)
            except Order.DoesNotExist:
                return JsonResponse({"error": "Commande introuvable"}, status=404)

            payment_status = data.get("status")
            if payment_status == "ACCEPTED":
                order.status = "PAID"
            elif payment_status in ["REFUSED", "CANCELLED"]:
                order.status = "CANCELLED"
            else:
                order.status = "PENDING"
            order.save()

            return JsonResponse({"message": "Commande mise à jour", "order_status": order.status}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Méthode non autorisée"}, status=405)
