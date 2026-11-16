from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import UserSettings
from .forms import UserSettingsForm


@login_required
def settings_view(request):
    user_settings, _ = UserSettings.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = UserSettingsForm(request.POST, instance=user_settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Settings saved successfully!')
            return redirect('user_settings')
    else:
        form = UserSettingsForm(instance=user_settings)

    return render(request, 'user_settings/settings.html', {
        'form': form,
        'settings': user_settings,
    })
