from django import forms
from .models import UserSettings


class UserSettingsForm(forms.ModelForm):
    class Meta:
        model = UserSettings
        fields = ['dark_mode', 'email_notifications']
        widgets = {
            'dark_mode': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-slate-900 rounded border-slate-300 focus:ring-slate-900'}),
            'email_notifications': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-slate-900 rounded border-slate-300 focus:ring-slate-900'}),
        }
