from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.html import format_html
from django.core.files.base import ContentFile

from .forms_admin import ImportZipForm

from .models import Exam, Subject, Pack, Order, OrderItem, Payment, DownloadToken, Profile, FreeSample, Notification
import os
import uuid

User = get_user_model()

# Branding de l'admin
admin.site.site_header = "Examhub — Backoffice"
admin.site.site_title = "Examhub — Backoffice"
admin.site.index_title = "Tableau de bord"


# --- Admin pour les modèles métiers ---
@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "is_long_model", "active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "active")


@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    list_display = ("exam", "pack_type", "subject", "years_range", "price", "is_active", "file_link")
    list_filter = ("exam", "pack_type", "is_active")
    search_fields = ("exam__name", "subject__name")
    fields = ("exam", "pack_type", "subject", "years_range", "price", "is_active", "file")
    actions = ["clear_zip", "import_zip"]

    # --- Lien de téléchargement dans la colonne FICHIER ZIP ---
    @admin.display(description="Fichier ZIP")
    def file_link(self, obj):
        """
        Affiche un lien cliquable si un fichier est associé au Pack.
        Recharge l’objet pour être sûr d’avoir la version la plus récente.
        """
        pack = Pack.objects.get(pk=obj.pk)
        if pack.file and pack.file.name:
            try:
                url = pack.file.url  # lève une exception si stockage privé
            except Exception:
                url = reverse("exams:admin_pack_download", args=[pack.pk])
            return format_html("<a href='{}' target='_blank'>Télécharger (admin)</a>", url)
        return "—"

    @admin.action(description="Supprimer le fichier ZIP")
    def clear_zip(self, request, queryset):
        deleted = 0
        for obj in queryset:
            if obj.file:
                try:
                    storage = obj.file.storage
                    path = obj.file.name
                    obj.file.delete(save=False)
                    obj.file = None
                    obj.save(update_fields=["file"])
                    if storage.exists(path):
                        storage.delete(path)
                    deleted += 1
                except Exception:
                    pass
        self.message_user(request, f"{deleted} fichier(s) supprimé(s).")

    @admin.action(description="Importer un fichier ZIP")
    def import_zip(self, request, queryset):
        if "apply" in request.POST:
            form = ImportZipForm(request.POST, request.FILES)
            if form.is_valid():
                uploaded = form.cleaned_data["zip_file"]
                data = uploaded.read()

                updated = 0
                for pack in queryset:
                    # supprime l'éventuel ancien fichier
                    if pack.file:
                        try:
                            old_storage = pack.file.storage
                            old_path = pack.file.name
                            pack.file.delete(save=False)
                            if old_storage.exists(old_path):
                                old_storage.delete(old_path)
                        except Exception:
                            pass

                    # nom unique
                    base = os.path.splitext(os.path.basename(uploaded.name))[0]
                    unique_name = f"{base}-{uuid.uuid4().hex[:8]}.zip"

                    # sauvegarde dans le stockage protégé
                    pack.file.save(f"packs/{unique_name}", ContentFile(data), save=False)
                    pack.save(update_fields=["file"])
                    updated += 1

                self.message_user(request, f"{updated} pack(s) mis à jour avec le fichier ZIP.")
                # force le rechargement de la liste => la colonne "Fichier ZIP" s'actualise
                from django.http import HttpResponseRedirect
                return HttpResponseRedirect(reverse("admin:exams_pack_changelist"))
        else:
            form = ImportZipForm()

        return render(request, "admin/import_zip.html", {
            "packs": queryset,
            "form": form,
            "action": "import_zip",
            "title": "Importer un fichier ZIP pour les packs sélectionnés",
        })


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "email", "phone", "status", "total_amount", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "email", "phone")


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "pack", "unit_price")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "provider", "reference", "amount", "status", "created_at")


@admin.register(DownloadToken)
class DownloadTokenAdmin(admin.ModelAdmin):
    list_display = ("item", "token", "expires_at", "remaining_downloads")


# --- Inline Profile dans la fiche User ---
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Profil utilisateur'
    fk_name = 'user'
    fields = ('role',)

# --- FreeSample (extraits publics) ------------------------------------------
@admin.register(FreeSample)
class FreeSampleAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'uploaded_at')
    list_filter = ('is_active', 'uploaded_at')
    search_fields = ('title',)
    readonly_fields = ('uploaded_at',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # si on en active un, désactiver les autres
        if obj.is_active:
            FreeSample.objects.exclude(pk=obj.pk).update(is_active=False)

# --- Personnaliser l'admin User: afficher le rôle et actions pour basculer ---
class CustomUserAdmin(DjangoUserAdmin):
    inlines = (ProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_role')
    search_fields = ('username', 'email')
    actions = ['make_users_client', 'make_users_admin']

    def get_role(self, obj):
        return getattr(getattr(obj, 'profile', None), 'role', '—')
    get_role.short_description = 'Rôle'

    @admin.action(description='Basculer sélection en CLIENT')
    def make_users_client(self, request, queryset):
        for user in queryset:
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = 'client'
            profile.save()

    @admin.action(description='Basculer sélection en ADMINISTRATEUR MÉTIER')
    def make_users_admin(self, request, queryset):
        for user in queryset:
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = 'administrator'
            profile.save()


# On remplace l'enregistrement par défaut de User par notre CustomUserAdmin
try:
    admin.site.unregister(User)
except Exception:
    pass

admin.site.register(User, CustomUserAdmin)


# --- Admin pour Profile ---
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email')
    actions = ['make_client', 'make_admin']

    @admin.action(description="Basculer en CLIENT")
    def make_client(self, request, queryset):
        for profile in queryset:
            profile.role = 'client'
            profile.save()

    @admin.action(description="Basculer en ADMINISTRATEUR MÉTIER")
    def make_admin(self, request, queryset):
        for profile in queryset:
            profile.role = 'administrator'
            profile.save()


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'read', 'created_at')
    list_filter = ('read', 'created_at')
    search_fields = ('user__username', 'message')
