from django.shortcuts import render
from django.contrib.auth.decorators import login_required


# home screen (protected)
@login_required
def home(request):
    return render(request, 'dashboard/home.html')
