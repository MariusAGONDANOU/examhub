from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse
from django.conf import settings
from .forms import UserUpdateForm, ProfileUpdateForm
from .models import Order, Notification
from pathlib import Path
from django.views.decorators.csrf import csrf_exempt 
from openai import OpenAI

import os
import json
import uuid

def _has_paid(user):
    return Order.objects.filter(user=user, status='PAID').exists()

@login_required
def my_profile(request):
    user_form = UserUpdateForm(request.POST or None, instance=request.user)
    profile_form = ProfileUpdateForm(
        request.POST or None,
        request.FILES or None,
        instance=request.user.profile
    )

    if request.method == "POST" and user_form.is_valid() and profile_form.is_valid():
        user_form.save()
        profile_form.save()
        messages.success(request, "Profil mis à jour.")
        return redirect("exams:my_profile")

    ctx = {
        "user_form": user_form,
        "profile_form": profile_form,
        "active_menu": "profile",
    }
    return render(request, "account/profile.html", ctx)

@login_required
@require_POST
def delete_account(request):
    u = request.user
    logout(request)
    u.delete()
    messages.success(request, "Votre compte a été supprimé avec succès.")
    return redirect("/")

@login_required
def chatbot(request):
    """
    Affiche l'interface du chatbot.
    """
    locked = not _has_paid(request.user)
    return render(request, "chatbot.html", {"active_menu": "qa", "locked": locked})

@login_required
@require_POST
def chatbot_upload(request):
    """
    Upload d'un fichier par l'utilisateur pour l'utiliser comme contexte dans le chat.
    Stocke une référence dans la session (chat_attachments).
    Retourne JSON {ok: True, id, name, url, text}
    """
    if not _has_paid(request.user):
        return JsonResponse({'error': 'paywall'}, status=403)

    uploaded = request.FILES.get('file')
    if not uploaded:
        return JsonResponse({'error': 'no_file_provided'}, status=400)

    # Préparer le dossier d'upload dans MEDIA_ROOT/chat_uploads
    upload_dir = os.path.join(str(settings.MEDIA_ROOT), 'chat_uploads')
    os.makedirs(upload_dir, exist_ok=True)

    # Nom unique
    ext = os.path.splitext(uploaded.name)[1]
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, unique_name)

    # Sauvegarde
    with open(file_path, 'wb') as dst:
        for chunk in uploaded.chunks():
            dst.write(chunk)

    # URL publique relative (servie par MEDIA_URL)
    url = settings.MEDIA_URL.rstrip('/') + '/chat_uploads/' + unique_name

    # Essayer d'extraire un extrait texte pour PDF si PyPDF2 est installé
    text_snippet = ""
    try:
        if ext.lower() == '.pdf':
            try:
                import PyPDF2
                with open(file_path, 'rb') as fp:
                    reader = PyPDF2.PdfReader(fp)
                    pages_to_read = min(len(reader.pages), 10)
                    extracted = []
                    for p in range(pages_to_read):
                        try:
                            page_text = reader.pages[p].extract_text() or ""
                            extracted.append(page_text)
                        except Exception:
                            continue
                    text_snippet = "\n".join(extracted).strip()[:4000]  # limiter la taille
            except Exception:
                text_snippet = ""
    except Exception:
        text_snippet = ""

    # Sauvegarder la métadonnée en session
    attachments = request.session.get('chat_attachments', [])
    attachments.append({
        'id': unique_name,
        'name': uploaded.name,
        'url': url,
        'text': text_snippet,
    })
    request.session['chat_attachments'] = attachments
    request.session.modified = True

    return JsonResponse({'ok': True, 'id': unique_name, 'name': uploaded.name, 'url': url, 'text': text_snippet})


@login_required
@require_POST
def chatbot_ask(request):
    """
    Reçoit JSON {"question": "...", "attachments": ["id1","id2", ...]}
    Envoie la requête à l'API OpenAI, stocke l'historique en session et retourne la réponse.
    """
    if not _has_paid(request.user):
        return JsonResponse({'error': 'paywall'}, status=403)

    try:
        data = json.loads(request.body.decode('utf-8') or "{}")
    except Exception:
        data = {}

    question = (data.get('question') or "").strip()
    attachments_ids = data.get('attachments') or []

    if not question and not attachments_ids:
        return JsonResponse({'error': 'empty_question'}, status=400)

    # Récupérer historique côté serveur
    history = request.session.get('chat_history', [])

    # Ajouter le message utilisateur dans l'historique
    history.append({'role': 'user', 'content': question})

    # Construire le prompt / messages à envoyer à l'API
    system_prompt = (
        "Tu es l'assistant d'Examhub. Tu expliques les solutions pas à pas, "
        "tu donnes des explications pédagogiques et des exemples si nécessaire. "
        "Si une question manque d'information, demande une précision poliment. "
        "Réponds en français."
    )

    messages = [{'role': 'system', 'content': system_prompt}]

    # Injecter le contenu des fichiers uploadés (si id fournis)
    session_attachments = request.session.get('chat_attachments', [])
    for aid in attachments_ids:
        m = next((a for a in session_attachments if a.get('id') == aid), None)
        if m:
            attach_text = (
                f"Fichier uploadé: {m.get('name')}\n"
                f"URL: {m.get('url')}\n"
                "Extrait (si disponible) :\n"
                f"{m.get('text','(aucun extrait)')}\n"
            )
            messages.append({'role': 'system', 'content': attach_text})

    # Ajouter l'historique (on garde les 20 derniers rôles pour le contexte)
    if isinstance(history, list):
        messages.extend(history[-20:])

    # Config OpenAI
    openai_api_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    if not openai_api_key:
        return JsonResponse({'error': 'openai_api_key_missing'}, status=500)

    client = OpenAI(api_key=openai_api_key)
    model = getattr(settings, "OPENAI_MODEL", "gpt-4o") or "gpt-4o"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=1200,
        )
        assistant_text = response.choices[0].message.content
    except Exception as e:
        return JsonResponse({'error': 'openai_error', 'detail': str(e)}, status=500)

    # Sauvegarder la réponse dans l'historique et dans la session (on garde 40 derniers messages)
    history.append({'role': 'assistant', 'content': assistant_text})
    request.session['chat_history'] = history[-40:]
    request.session.modified = True

    return JsonResponse({'answer': assistant_text})


@login_required
@require_POST
def chatbot_clear(request):
    """
    Réinitialise l'historique et les fichiers attachés (session).
    """
    if 'chat_history' in request.session:
        del request.session['chat_history']
    if 'chat_attachments' in request.session:
        del request.session['chat_attachments']
    request.session.modified = True
    return JsonResponse({'ok': True})

@login_required
def notifications_list(request):
    notifs = Notification.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'notifications.html', {'notifications': notifs})

@login_required
def notifications_mark_read(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.read = True
    n.save(update_fields=['read'])
    return redirect('exams:notifications_list')

@login_required
def notifications_delete(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.delete()
    return redirect('exams:notifications_list')

@login_required
def notifications_mark_all_read(request):
    """Marquer toutes les notifications de l'utilisateur comme lues."""
    Notification.objects.filter(user=request.user, read=False).update(read=True)
    messages.success(request, "Toutes les notifications ont été marquées comme lues.")
    return redirect('exams:notifications_list')

@login_required
def notifications_delete_all(request):
    """Supprimer toutes les notifications de l'utilisateur."""
    Notification.objects.filter(user=request.user).delete()
    messages.success(request, "Toutes vos notifications ont été supprimées.")
    return redirect('exams:notifications_list')
