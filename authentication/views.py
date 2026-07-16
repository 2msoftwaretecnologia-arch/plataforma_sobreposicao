from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic.edit import CreateView

from .forms import OnboardingForm, RegisterForm
from .models import UserProfile


def _safe_next_url(request):
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return None


class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = 'authentication/register.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['next'] = self.request.GET.get('next', '')
        return context

    def get_success_url(self):
        next_url = _safe_next_url(self.request)
        onboarding_url = reverse('authentication:onboarding')
        return f'{onboarding_url}?next={next_url}' if next_url else onboarding_url

    def form_valid(self, form):
        response = super().form_valid(form)
        UserProfile.objects.get_or_create(user=self.object)
        login(self.request, self.object)
        return response


class CustomLoginView(LoginView):
    template_name = 'authentication/login.html'
    redirect_authenticated_user = True


class OnboardingView(View):
    template_name = 'authentication/onboarding.html'

    def get(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        form = OnboardingForm(instance=profile)
        return self._render(request, form)

    def post(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        form = OnboardingForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.onboarding_completo = True
            profile.save()
            return redirect(_safe_next_url(request) or 'landing_page')

        return self._render(request, form)

    def _render(self, request, form):
        return render(request, self.template_name, {
            'form': form,
            'next': _safe_next_url(request) or '',
        })
