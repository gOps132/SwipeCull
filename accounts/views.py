from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login


# register screen
def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user) # logs user in after registering
            return redirect('home')
    else:
        form = UserCreationForm()

    return render(request, 'accounts/register.html', {'form': form})
