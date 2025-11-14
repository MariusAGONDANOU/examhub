from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseBadRequest, FileResponse, Http404
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from .models import Exam, Pack, Order, OrderItem, Payment, DownloadToken, FreeSample
from .forms import PaymentForm
from .price_rules import compute_price
from datetime import timedelta
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, FileResponse, Http404, HttpResponse
from django.template.loader import render_to_string

import uuid
import os

def index(request):
    q = (request.GET.get('q') or "").strip()
    exams = Exam.objects.filter(active=True)
    if q:
        # Recherche intuitive: commence par (comme demandé)
        exams = exams.filter(name__istartswith=q)

    # Si requête AJAX: on renvoie seulement le fragment HTML des cartes
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('partials/exam_cards.html', {'exams': exams}, request=request)
        return HttpResponse(html)

    return render(request, 'index.html', {'exams': exams, 'q': q, "active_menu": "exams"})

def exam_detail(request, slug):
    exam = get_object_or_404(Exam, slug=slug, active=True)
    packs = Pack.objects.filter(exam=exam, is_active=True)
    ctx = {
        "exam": exam,
        "packs": packs,
        "active_menu": "packs",
    }
    return render(request, 'exam_detail.html', ctx)

def create_order(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('Méthode invalide')

    form = PaymentForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'ok': False, 'errors': form.errors}, status=400)

    operator = form.cleaned_data['operator']
    phone = form.cleaned_data['phone']
    email = form.cleaned_data.get('email') or ''
    pack_id = form.cleaned_data['pack_id']

    pack = get_object_or_404(Pack, pk=pack_id, is_active=True)

    price = compute_price(pack.exam, pack.pack_type, pack.subject.code if pack.subject else None)

    order = Order.objects.create(
        user=request.user if request.user.is_authenticated else None,
        phone=phone,
        email=email,
        total_amount=price,
    )
    OrderItem.objects.create(order=order, pack=pack, unit_price=price)

    payment_ref = uuid.uuid4().hex[:12]
    Payment.objects.create(
        order=order,
        provider=operator if settings.PAYMENT_PROVIDER != 'SIMULATOR' else 'SIMULATOR',
        reference=payment_ref,
        amount=price,
        status='PENDING'
    )

    confirm_url = reverse('exams:order_confirm', args=[order.id])
    return JsonResponse({'ok': True, 'redirect': confirm_url})

def order_confirm(request, order_id):
    from datetime import timedelta
    order = get_object_or_404(Order, pk=order_id)

    if request.method == 'POST':
        payment = get_object_or_404(Payment, order=order)
        payment.status = 'SUCCESS'
        payment.save()
        order.status = 'PAID'
        order.save()

        for item in order.items.all():
            expires = timezone.now() + timedelta(hours=settings.DOWNLOAD_TOKEN_TTL_HOURS)
            DownloadToken.objects.update_or_create(
                item=item,
                defaults={'expires_at': expires, 'remaining_downloads': settings.DOWNLOAD_MAX_TIMES}
            )
        messages.success(request, 'Paiement confirmé. Vos téléchargements sont prêts.')
        return redirect('exams:order_confirm', order_id=order.id)

    tokens = []
    if order.status == 'PAID':
        for item in order.items.select_related('pack'):
            try:
                t = DownloadToken.objects.get(item=item)
                tokens.append(t)
            except DownloadToken.DoesNotExist:
                pass

    return render(request, 'order_confirm.html', {'order': order, 'tokens': tokens})

@csrf_exempt
def payment_webhook(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('Méthode invalide')
    ref = request.POST.get('reference')
    status = request.POST.get('status')
    try:
        payment = Payment.objects.get(reference=ref)
    except Payment.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'payment not found'}, status=404)

    payment.status = status
    payment.raw_payload = dict(request.POST)
    payment.save()

    if status == 'SUCCESS':
        order = payment.order
        order.status = 'PAID'
        order.save()
        for item in order.items.all():
            expires = timezone.now() + timedelta(hours=settings.DOWNLOAD_TOKEN_TTL_HOURS)
            DownloadToken.objects.update_or_create(
                item=item,
                defaults={'expires_at': expires, 'remaining_downloads': settings.DOWNLOAD_MAX_TIMES}
            )
    return JsonResponse({'ok': True})

@login_required
def download_file(request, token):
    """
    Téléchargement client via token :
    - token valide et non expiré
    - l'utilisateur connecté doit posséder la commande (sauf staff)
    - envoi du ZIP en pièce jointe
    """
    t = get_object_or_404(
        DownloadToken.objects.select_related('item__order', 'item__pack'),
        token=token
    )
    if not t.is_valid():
        messages.error(request, 'Lien de téléchargement expiré ou nombre de téléchargements atteint.')
        return redirect('exams:index')

    order = t.item.order
    owner = getattr(order, 'user', None)
    if owner and (request.user != owner) and (not request.user.is_staff):
        messages.error(request, "Ce lien ne vous appartient pas.")
        return redirect('exams:index')

    pack = t.item.pack
    if not pack.file:
        messages.error(request, "Aucun fichier n'est associé à ce pack. Contactez l'administrateur.")
        return redirect('exams:index')

    file_path = pack.file.path
    if not os.path.exists(file_path):
        messages.error(request, "Le fichier demandé est introuvable. Contactez l'administrateur.")
        return redirect('exams:index')

    # Décrémenter le compteur
    t.remaining_downloads -= 1
    t.save(update_fields=['remaining_downloads'])

    resp = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=os.path.basename(file_path))
    resp['Content-Type'] = 'application/zip'
    resp['X-Content-Type-Options'] = 'nosniff'
    try:
        resp['Content-Length'] = os.path.getsize(file_path)
    except Exception:
        pass
    return resp

# --- Extraits (libres d’accès) ----------------------------------------------

def free_sample_page(request):
    """
    Affiche la page des extraits.
    On prend le plus récent objet actif, s'il existe.
    """
    sample = FreeSample.objects.filter(is_active=True).order_by('-uploaded_at').first()
    ctx = {
        'sample': sample,
        'active_menu': 'free_sample',
    }
    return render(request, 'free_sample.html', ctx)


def free_sample_download(request, pk):
    """
    Renvoie le ZIP en téléchargement direct (public).
    """
    sample = get_object_or_404(FreeSample, pk=pk, is_active=True)
    if not sample.file:
        raise Http404("Aucun fichier pour cet extrait.")
    file_path = sample.file.path
    if not os.path.exists(file_path):
        raise Http404("Fichier introuvable.")

    resp = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=os.path.basename(file_path))
    resp['Content-Type'] = 'application/zip'
    resp['X-Content-Type-Options'] = 'nosniff'
    try:
        resp['Content-Length'] = os.path.getsize(file_path)
    except Exception:
        pass
    return resp

@staff_member_required
def admin_pack_download(request, pk):
    """
    Téléchargement du ZIP côté back-office (staff uniquement).
    """
    pack = get_object_or_404(Pack, pk=pk)
    if not pack.file:
        raise Http404("Aucun fichier pour ce pack.")
    file_path = pack.file.path
    if not os.path.exists(file_path):
        raise Http404("Fichier introuvable.")
    resp = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=os.path.basename(file_path))
    resp['Content-Type'] = 'application/zip'
    resp['X-Content-Type-Options'] = 'nosniff'
    try:
        resp['Content-Length'] = os.path.getsize(file_path)
    except Exception:
        pass
    return resp
