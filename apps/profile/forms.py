from django import forms
from .models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['full_name', 'bio', 'profile_image']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900'}),
            'bio': forms.Textarea(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:border-slate-900', 'rows': 4}),
            'profile_image': forms.FileInput(attrs={'class': 'w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200'}),
        }
