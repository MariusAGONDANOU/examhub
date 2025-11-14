from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.utils import timezone
from django.db.models import JSONField
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import FileExtensionValidator
from .storages import ProtectedStorage

import uuid

class Exam(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    level = models.CharField(max_length=50, choices=[
        ('BAC', 'BAC'),
        ('DTI/STI', 'DTI/STI'),
        ('CAP/CB', 'CAP/CB'),
        ('BEPC', 'BEPC'),
    ])
    is_long_model = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class Subject(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)  # MATH, PCT
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

def validate_zip(value):
    """
    Valide qu'on reçoit bien un .zip SAFE :
    - extension .zip uniquement
    - taille maximale 500 Mo
    - nombre de fichiers raisonnable
    - ratio de décompression limité (anti zip-bomb)
    """
    name = value.name.lower()
    if not name.endswith(".zip"):
        raise ValidationError("Seuls les fichiers .zip sont autorisés.")

    max_size_bytes = 500 * 1024 * 1024  # 500 Mo
    if hasattr(value, "size") and value.size and value.size > max_size_bytes:
        raise ValidationError("Le ZIP ne doit pas dépasser 500 Mo.")

    # Contrôles de structure avec zipfile
    import zipfile
    try:
        pos = value.tell()
    except Exception:
        pos = None
    try:
        with zipfile.ZipFile(value) as zf:
            infos = zf.infolist()
            if len(infos) > 5000:
                raise ValidationError("Le ZIP contient trop de fichiers (>5000).")

            total_uncompressed = sum(i.file_size for i in infos)
            total_compressed = sum(i.compress_size for i in infos) or 1
            # ratio de décompression
            ratio = total_uncompressed / float(total_compressed)
            if ratio > 100:  # très conservateur
                raise ValidationError("ZIP suspect (ratio de décompression trop élevé).")
    except zipfile.BadZipFile:
        raise ValidationError("Fichier ZIP invalide ou corrompu.")
    finally:
        try:
            if pos is not None:
                value.seek(pos)
        except Exception:
            pass

class Pack(models.Model):
    TYPE_CHOICES = [
        ('SINGLE', 'Matière seule'),
        ('DOUBLE', 'Deux matières (Math + PCT)'),
    ]
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    pack_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    years_range = models.CharField(max_length=30, default='2015–2025')
    price = models.PositiveIntegerField(default=0)  # en F CFA
    file = models.FileField(
        storage=ProtectedStorage(),
        upload_to='packs/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(['zip']), validate_zip],
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('exam', 'pack_type', 'subject')

    def __str__(self):
        base = f"{self.exam.name} {self.get_pack_type_display()}"
        if self.pack_type == 'SINGLE' and self.subject:
            base += f" — {self.subject.name}"
        return base

    def save(self, *args, **kwargs):
        # Auto-align price with rules
        try:
            from .price_rules import compute_price
            computed = compute_price(self.exam, self.pack_type, self.subject.code if self.subject else None)
            if computed:
                self.price = computed
        except Exception:
            pass
        super().save(*args, **kwargs)

# --- Extrait (ZIP libre d’accès) ---------------------------------------------

class FreeSample(models.Model):
    """
    Un ZIP public (prévisualisation) ajouté par l'admin métier.
    On n'en affiche qu'un (le plus récent actif) côté client.
    """
    title = models.CharField(max_length=150, default="Extrait Épreuve + Corrigé")
    file = models.FileField(
        upload_to='free_samples/',
        validators=[FileExtensionValidator(['zip']), validate_zip],
        help_text="Fichier .zip (max ~500Mo, contrôles anti zip-bomb)."
    )
    is_active = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title

class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'En attente'),
        ('PAID', 'Payée'),
        ('CANCELLED', 'Annulée'),
    ]

    PAYMENT_CHOICES = [
        ('MOBILEMONEY', 'Mobile Money'),
        ('STRIPE', 'Carte bancaire (Stripe)'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    total_amount = models.PositiveIntegerField(default=0)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='MOBILEMONEY')
    created_at = models.DateTimeField(auto_now_add=True)
    stripe_session_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="ID de la session Stripe Checkout"
    )

    def __str__(self):
        return f"Order #{self.pk} - {self.status} - {self.payment_method}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)   # 👈 AJOUT DE CE CHAMP

    def __str__(self):
        return f"{self.pack.title} (x{self.quantity})"

class Payment(models.Model):
    PROVIDERS = [
        ('MTN', 'MTN'), ('MOOV', 'MOOV'), ('CELTIIS', 'Celtiis'), ('SIMULATOR', 'Simulator')
    ]
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    provider = models.CharField(max_length=20, choices=PROVIDERS)
    reference = models.CharField(max_length=100, unique=True)
    amount = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default='PENDING')  # PENDING/SUCCESS/FAILED
    created_at = models.DateTimeField(auto_now_add=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Payment {self.reference} - {self.status}"

class DownloadToken(models.Model):
    item = models.OneToOneField(OrderItem, on_delete=models.CASCADE)
    token = models.CharField(max_length=64, unique=True, default='')
    expires_at = models.DateTimeField()
    remaining_downloads = models.PositiveIntegerField(default=3)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def is_valid(self):
        return self.remaining_downloads > 0 and timezone.now() < self.expires_at

    def __str__(self):
        return f"Token for {self.item} (expires {self.expires_at})"

class Profile(models.Model):
    ROLE_CHOICES = [
        ('client', 'Client'),
        ('admin_metier', 'Administrateur métier'),
    ]
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='client')

    # AJOUTS
    phone = models.CharField(max_length=30, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

# --- PANIER ---------------------------------------------------------------

class Cart(models.Model):
    """
    Panier persistant, lié à un utilisateur.
    Un utilisateur = un panier actif au plus.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart(user={self.user.username})"

    @property
    def items_count(self):
        return self.items.count()

    @property
    def total_amount(self):
        return sum(i.subtotal for i in self.items.select_related('pack'))

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('cart', 'pack')

    def __str__(self):
        return f"{self.pack} x{self.quantity}"

    @property
    def unit_price(self):
        # on s'appuie sur le prix du Pack
        return self.pack.price

    @property
    def subtotal(self):
        return self.unit_price * self.quantity
        
# --- POSSESSION APRES PAIEMENT -------------------------------------------

class PurchasedPack(models.Model):
    """
    Pack possédé par l'utilisateur suite à un paiement validé.
    Evite les doubles entrées (user, pack) uniques.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='purchases')
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE, related_name='purchases')
    acquired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'pack')

    def __str__(self):
        return f"{self.user} possède {self.pack}"

class Notification(models.Model):
    """
    Notification simple (comme Facebook/LinkedIn).
    message : texte lisible
    payload : données utiles (packs, urls de téléchargement, total, etc.)
    read    : pour compter les non lues
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    message = models.TextField()
    payload = JSONField(default=dict, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notif {self.id} -> {self.user} ({'lu' if self.read else 'non lu'})"

# --- Signals utiles pour créer le Profile automatiquement et synchroniser les droits Django ---
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()

@receiver(post_save, sender=User)
def create_profile_for_new_user(sender, instance, created, **kwargs):
    """Créer automatiquement un Profile lorsqu'un User est créé."""
    if created:
        Profile.objects.get_or_create(user=instance)

@receiver(post_save, sender=Profile)
def sync_user_flags_from_role(sender, instance, **kwargs):
    """Synchroniser les flags is_staff/is_superuser en fonction du rôle métier."""
    u = instance.user
    if instance.role == 'administrator':
        changed = False
        if not u.is_staff:
            u.is_staff = True
            changed = True
        if not u.is_superuser:
            u.is_superuser = True
            changed = True
        if changed:
            u.save(update_fields=['is_staff', 'is_superuser'])
    else:
        # si rôle != administrator : s'assurer que les flags admin sont révoqués
        if u.is_staff or u.is_superuser:
            u.is_staff = False
            u.is_superuser = False
            u.save(update_fields=['is_staff', 'is_superuser'])
