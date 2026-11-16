from django.contrib.auth.models import User
from django.db import models


class DriveConnection(models.Model):
    """OAuth connection to a cloud storage provider (e.g. Google Drive)."""

    PROVIDER_CHOICES = (
        ('google_drive', 'Google Drive'),
        ('dropbox', 'Dropbox'),
        ('onedrive', 'OneDrive'),
        ('icloud', 'iCloud'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='drive_connections')
    provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES, default='google_drive')
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True, null=True)
    token_expiry = models.DateTimeField(blank=True, null=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'drive_connection'
        ordering = ['-connected_at']
        verbose_name = 'Drive Connection'
        verbose_name_plural = 'Drive Connections'

    def __str__(self):
        return f"{self.user.username} — {self.get_provider_display()}"


class CullSession(models.Model):
    """A single culling session for a specific folder/source."""

    STATUS_CHOICES = (
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cull_sessions')
    drive_connection = models.ForeignKey(DriveConnection, on_delete=models.CASCADE, related_name='cull_sessions')
    folder_name = models.CharField(max_length=255, blank=True)
    folder_id = models.CharField(max_length=255, blank=True)
    total_files = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'cull_session'
        ordering = ['-created_at']
        verbose_name = 'Cull Session'
        verbose_name_plural = 'Cull Sessions'

    def __str__(self):
        return f"{self.user.username} / {self.folder_name} ({self.status})"


class MediaFile(models.Model):
    """A file within a cull session — supports photos, videos, documents, and audio."""

    FILE_TYPE_CHOICES = (
        ('photo', 'Photo'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('audio', 'Audio'),
        ('other', 'Other'),
    )

    session = models.ForeignKey(CullSession, on_delete=models.CASCADE, related_name='media_files')
    drive_file_id = models.CharField(max_length=255, unique=True)
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, default='photo')
    mime_type = models.CharField(max_length=100, blank=True)
    file_size_mb = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    width = models.IntegerField(blank=True, null=True)
    height = models.IntegerField(blank=True, null=True)
    duration_seconds = models.IntegerField(blank=True, null=True)
    taken_at = models.DateTimeField(blank=True, null=True)
    thumbnail_url = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'media_file'
        ordering = ['taken_at', 'file_name']
        verbose_name = 'Media File'
        verbose_name_plural = 'Media Files'

    def __str__(self):
        return f"{self.file_name} ({self.file_type})"


class SwipeDecision(models.Model):
    """Records a keep/trash decision made by a user on a specific file."""

    DECISION_CHOICES = [
        ('keep', 'Keep'),
        ('trash', 'Trash'),
    ]

    media_file = models.ForeignKey(MediaFile, on_delete=models.CASCADE, related_name='swipe_decisions')
    session = models.ForeignKey(CullSession, on_delete=models.CASCADE, related_name='swipe_decisions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='swipe_decisions')
    decision = models.CharField(max_length=10, choices=DECISION_CHOICES)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'swipe_decision'
        ordering = ['-decided_at']
        unique_together = ('media_file', 'session', 'user')
        verbose_name = 'Swipe Decision'
        verbose_name_plural = 'Swipe Decisions'

    def __str__(self):
        return f"{self.user.username} → {self.decision} — {self.media_file.file_name}"
