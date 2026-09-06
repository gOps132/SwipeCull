from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required

# home screen (protected)
@login_required
def home(request):
    return render(request, 'main/home.html')

# register screen
def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user) # logs user in after requesting
            return redirect('home')
    else:
        form = UserCreationForm()
    
    return render(request, 'main/register.html', {'form': form})