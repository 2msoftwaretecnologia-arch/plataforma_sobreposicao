from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.http import HttpRequest

@require_http_methods(["GET", "POST"]) 
def login_view(request: HttpRequest):
    if request.user.is_authenticated:
        next_url = request.GET.get('next') or request.POST.get('next')
        return redirect(next_url or '/')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        next_url = request.POST.get('next')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(next_url or '/')
        else:
            messages.error(request, 'Usuário ou senha inválidos.')

    context = { 'next': request.GET.get('next', '') }
    return render(request, 'login/login.html', context)

@require_http_methods(["POST", "GET"]) 
def logout_view(request: HttpRequest):
    logout(request)
    return redirect('/')
