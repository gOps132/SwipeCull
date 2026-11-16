from django.contrib import admin
from .models import DriveConnection, CullSession, MediaFile, SwipeDecision

admin.site.register(DriveConnection)
admin.site.register(CullSession)
admin.site.register(MediaFile)
admin.site.register(SwipeDecision)
